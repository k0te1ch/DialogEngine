"""Связка движка, клавиатуры, хранилища и доставки.

Методы принимают примитивы (строку ``callback_data``, текст сообщения), а не
объекты aiogram. Так логика шага проверяется тестами без бота и без сети, а
разбор апдейтов остаётся тонкой прослойкой в :mod:`.router`.

Про «Назад»: :meth:`~dialog_engine.DialogEngine.back` и
:meth:`~dialog_engine.DialogEngine.jump_to` **стирают** ответ того шага, на
который возвращаются (``session.answers.pop(...)``). Для интерфейса это
неочевидно — пользователь ждёт увидеть свой прежний выбор отмеченным, а его
уже нет. Здесь поведение движка не переопределяется, но о нём стоит помнить:
если нужен возврат с сохранением ответа, потребителю придётся запомнить
значение до вызова и подставить его самому.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aiogram.fsm.context import FSMContext

from dialog_engine.engine import DialogEngine
from dialog_engine.exceptions import DialogError, ValidationError
from dialog_engine.session import DialogSession
from dialog_engine.step import DialogStep

from .callbacks import CallbackParseError, DialogAction, DialogCallback, step_token
from .keyboards import DEFAULT_LAYOUT, KeyboardLayout, render_keyboard, step_options
from .storage import DialogUIState, FSMDialogStorage
from .views import DialogSender, StepView

BUTTON_ONLY_TYPES = frozenset({"choice", "multi_choice", "boolean"})
"""Типы шагов, на которых текстовый ввод не принимается."""

NO_SESSION_ALERT = "Диалог не запущен или уже завершён."
STALE_BUTTON_ALERT = "Кнопка устарела — ответьте на текущий вопрос."
BUTTON_REQUIRED_ERROR = "Выберите вариант с помощью кнопок."


@dataclass(frozen=True, slots=True)
class DialogTurn:
    """Итог обработки одного действия пользователя."""

    handled: bool = True
    """``False``, если действие к диалогу не относится (чужая кнопка, нет сессии)."""

    finished: bool = False
    cancelled: bool = False
    answers: dict[str, Any] = field(default_factory=dict)
    """Собранные ответы — заполняются при ``finished``."""

    alert: str | None = None
    """Короткое уведомление, которое стоит показать всплывающим окном."""


class DialogRunner:
    """Проводит пользователя по анкете, ничего не отправляя напрямую."""

    def __init__(
        self,
        engine: DialogEngine,
        *,
        layout: KeyboardLayout = DEFAULT_LAYOUT,
        storage: FSMDialogStorage | None = None,
    ) -> None:
        self.engine = engine
        self.layout = layout
        self.storage = storage or FSMDialogStorage()

    # ── Запуск ────────────────────────────────────────────────────────────────

    async def start(self, state: FSMContext, sender: DialogSender) -> DialogTurn:
        """Начать анкету заново, отбросив предыдущую сессию в этом чате."""
        session = self.engine.create_session()
        ui = DialogUIState()
        await self._render(session, ui, sender)
        await self.storage.save(state, session, ui)
        return DialogTurn()

    async def cancel(self, state: FSMContext) -> DialogTurn:
        """Отменить текущую анкету и очистить сохранённое состояние."""
        session, _ui = await self.storage.load(state)
        if session is None:
            return DialogTurn(handled=False, alert=NO_SESSION_ALERT)
        self.engine.cancel(session)
        await self.storage.clear(state)
        return DialogTurn(cancelled=True)

    # ── Приём ответа ──────────────────────────────────────────────────────────

    async def on_callback(
        self, payload: str | None, state: FSMContext, sender: DialogSender
    ) -> DialogTurn:
        """Обработать нажатие inline-кнопки.

        Args:
            payload: содержимое ``callback_data``.
        """
        try:
            callback = DialogCallback.unpack(payload)
        except CallbackParseError:
            return DialogTurn(handled=False)

        session, ui = await self.storage.load(state)
        step = await self._require_step(session, state)
        if session is None or step is None:
            return DialogTurn(handled=False, alert=NO_SESSION_ALERT)

        if callback.step_token != step_token(step.id):
            # Нажали кнопку в сообщении от прошлого шага: молча подчиняться
            # такому нажатию опаснее, чем сказать, что оно устарело.
            return DialogTurn(alert=STALE_BUTTON_ALERT)

        return await self._dispatch(callback, step, session, ui, state, sender)

    async def on_text(
        self, text: str, state: FSMContext, sender: DialogSender
    ) -> DialogTurn:
        """Обработать текстовый ответ на шаг ``text`` / ``number`` / ``email``."""
        session, ui = await self.storage.load(state)
        step = await self._require_step(session, state)
        if session is None or step is None:
            return DialogTurn(handled=False, alert=NO_SESSION_ALERT)

        if step.type in BUTTON_ONLY_TYPES:
            await self._render(session, ui, sender, error=BUTTON_REQUIRED_ERROR)
            await self.storage.save(state, session, ui)
            return DialogTurn()

        return await self._submit(text, session, ui, state, sender)

    async def submit_value(
        self, value: Any, state: FSMContext, sender: DialogSender
    ) -> DialogTurn:
        """Ответить на текущий шаг произвольным значением.

        Нужно для шагов ``photo`` / ``file``, где ответ — список ``file_id``,
        а не текст: их извлечение из апдейта остаётся за потребителем.
        """
        session, ui = await self.storage.load(state)
        step = await self._require_step(session, state)
        if session is None or step is None:
            return DialogTurn(handled=False, alert=NO_SESSION_ALERT)
        return await self._submit(value, session, ui, state, sender)

    # ── Разбор действий ───────────────────────────────────────────────────────

    async def _dispatch(
        self,
        callback: DialogCallback,
        step: DialogStep,
        session: DialogSession,
        ui: DialogUIState,
        state: FSMContext,
        sender: DialogSender,
    ) -> DialogTurn:
        match callback.action:
            case DialogAction.NOOP:
                return DialogTurn()

            case DialogAction.PAGE:
                ui.page = callback.arg
                return await self._redraw(session, ui, state, sender)

            case DialogAction.PICK:
                return await self._pick(callback.arg, step, session, ui, state, sender)

            case DialogAction.DONE:
                return await self._submit(list(ui.selected), session, ui, state, sender)

            case DialogAction.SKIP:
                return await self._navigate(
                    lambda: self.engine.skip(session), session, ui, state, sender
                )

            case DialogAction.BACK:
                return await self._navigate(
                    lambda: self.engine.back(session), session, ui, state, sender
                )

            case DialogAction.CANCEL:
                self.engine.cancel(session)
                await self.storage.clear(state)
                return DialogTurn(cancelled=True)

        return DialogTurn(handled=False)

    async def _pick(
        self,
        index: int,
        step: DialogStep,
        session: DialogSession,
        ui: DialogUIState,
        state: FSMContext,
        sender: DialogSender,
    ) -> DialogTurn:
        """Нажатие на вариант ответа."""
        options = step_options(step, self.layout)
        if not 0 <= index < len(options):
            return DialogTurn(alert=STALE_BUTTON_ALERT)
        key = options[index].key

        if step.type != "multi_choice":
            return await self._submit(key, session, ui, state, sender)

        # Набор вариантов копится в состоянии интерфейса и уходит движку целиком
        # по кнопке «Готово» — промежуточные отметки ответом ещё не являются.
        if key in ui.selected:
            ui.selected.remove(key)
        else:
            ui.selected.append(key)
        return await self._redraw(session, ui, state, sender)

    async def _submit(
        self,
        value: Any,
        session: DialogSession,
        ui: DialogUIState,
        state: FSMContext,
        sender: DialogSender,
    ) -> DialogTurn:
        """Отдать значение движку и перейти к следующему шагу."""
        try:
            await self.engine.async_submit(session, value)
        except ValidationError as exc:
            # Шаг не сбрасывается: пользователь видит ошибку над тем же
            # вопросом и отвечает заново.
            await self._render(session, ui, sender, error=str(exc))
            await self.storage.save(state, session, ui)
            return DialogTurn()

        return await self._after_step(session, ui, state, sender)

    async def _navigate(
        self,
        action: Callable[[], Any],
        session: DialogSession,
        ui: DialogUIState,
        state: FSMContext,
        sender: DialogSender,
    ) -> DialogTurn:
        """Выполнить переход («Назад» / «Пропустить»), показав отказ движка."""
        try:
            action()
        except DialogError as exc:
            return DialogTurn(alert=str(exc))
        return await self._after_step(session, ui, state, sender)

    async def _after_step(
        self,
        session: DialogSession,
        ui: DialogUIState,
        state: FSMContext,
        sender: DialogSender,
    ) -> DialogTurn:
        """Общий хвост перехода: либо рисуем новый шаг, либо завершаем анкету."""
        ui.reset_step()
        if self.engine.current_step(session) is None:
            answers = dict(session.answers)
            await self.storage.clear(state)
            return DialogTurn(finished=True, answers=answers)
        return await self._redraw(session, ui, state, sender)

    async def _redraw(
        self,
        session: DialogSession,
        ui: DialogUIState,
        state: FSMContext,
        sender: DialogSender,
    ) -> DialogTurn:
        await self._render(session, ui, sender)
        await self.storage.save(state, session, ui)
        return DialogTurn()

    # ── Отрисовка ─────────────────────────────────────────────────────────────

    async def build_view(
        self,
        session: DialogSession,
        ui: DialogUIState,
        error: str | None = None,
    ) -> StepView | None:
        """Собрать представление текущего шага; ``None``, если анкета кончилась."""
        step = self.engine.current_step(session)
        if step is None:
            return None
        position, total = self.engine.progress(session)
        return StepView(
            text=await self.engine.async_resolve_text(step, session),
            keyboard=render_keyboard(
                step,
                page=ui.page,
                selected=ui.selected,
                can_go_back=position > 1,
                layout=self.layout,
            ),
            step=step,
            error=error,
            progress=(position, total),
        )

    async def _render(
        self,
        session: DialogSession,
        ui: DialogUIState,
        sender: DialogSender,
        error: str | None = None,
    ) -> None:
        view = await self.build_view(session, ui, error)
        if view is None:
            return
        ui.anchor = await sender.show(view, ui.anchor)

    async def _require_step(
        self, session: DialogSession | None, state: FSMContext
    ) -> DialogStep | None:
        """Текущий шаг живой сессии; ``None`` — с очисткой мусора в хранилище."""
        if session is None:
            return None
        step = self.engine.current_step(session)
        if step is None:
            await self.storage.clear(state)
        return step
