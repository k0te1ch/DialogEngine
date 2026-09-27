"""Хранение состояния диалога в ``FSMContext`` aiogram.

``DialogSession`` уже умеет ``to_dict()``/``from_dict()``, поэтому адаптеру
остаётся положить её рядом с состоянием интерфейса под одним ключом в данных
FSM. Это даёт главное: при перезапуске процесса (или при ``RedisStorage``)
анкета продолжается с того же шага и в том же сообщении.

Состояние интерфейса — номер страницы, отмеченные варианты, привязка к
сообщению — живёт отдельно от ``session.answers``. Страница пагинации это не
ответ пользователя, и ей нечего делать в результатах анкеты.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiogram.fsm.context import FSMContext

from dialog_engine.engine import DialogEngine
from dialog_engine.session import DialogSession

from .views import MessageAnchor

DEFAULT_STORAGE_KEY = "dialog_engine"


@dataclass
class DialogUIState:
    """Состояние отображения текущего шага."""

    page: int = 0
    selected: list[str] = field(default_factory=list)
    """Отмеченные, но ещё не подтверждённые варианты шага ``multi_choice``."""

    anchor: MessageAnchor | None = None

    def reset_step(self) -> None:
        """Сбросить всё, что относилось к предыдущему шагу.

        Привязка к сообщению переживает переход: следующий шаг должен
        перерисовать то же самое сообщение.
        """
        self.page = 0
        self.selected = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "selected": list(self.selected),
            "anchor": self.anchor.to_dict() if self.anchor else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DialogUIState:
        raw_anchor = data.get("anchor")
        return cls(
            page=int(data.get("page", 0)),
            selected=list(data.get("selected", [])),
            anchor=MessageAnchor.from_dict(raw_anchor) if raw_anchor else None,
        )


class FSMDialogStorage:
    """Чтение и запись состояния диалога в данных ``FSMContext``.

    Каждая анкета лежит под своим ключом, поэтому в одном чате их может идти
    несколько. :meth:`for_engine` строит ключ от ``dialog_id`` и сверяет
    восстановленную сессию с движком; голый конструктор оставлен для ключа,
    выбранного вручную.
    """

    def __init__(
        self,
        key: str = DEFAULT_STORAGE_KEY,
        *,
        engine: DialogEngine | None = None,
        legacy_keys: tuple[str, ...] = (),
    ) -> None:
        """Создать хранилище под ключом *key*.

        Args:
            key: ключ в данных FSM.
            engine: движок, через который восстанавливать сессию; чужая
                сессия (другой ``dialog_id`` или версия схемы) тогда
                считается отсутствующей.
            legacy_keys: ключи, под которыми сессия могла лежать раньше.
                Найденная там своя сессия переносится под *key*.
        """
        self.key = key
        self.engine = engine
        self.legacy_keys = legacy_keys

    @classmethod
    def for_engine(
        cls, engine: DialogEngine, scope: str | int | None = None
    ) -> FSMDialogStorage:
        """Хранилище анкеты *engine*: ключ ``dialog_engine:<dialog_id>``.

        *scope* разводит несколько копий одной анкеты в чате — например,
        подтверждение для конкретного сообщения (``scope=message_id``).
        Сессии, сохранённые до 0.3 под общим ключом, подхватываются.
        """
        key = f"{DEFAULT_STORAGE_KEY}:{engine.dialog_id}"
        if scope is not None:
            return cls(f"{key}:{scope}", engine=engine)
        return cls(key, engine=engine, legacy_keys=(DEFAULT_STORAGE_KEY,))

    async def load(
        self, state: FSMContext
    ) -> tuple[DialogSession | None, DialogUIState]:
        """Вернуть сохранённую сессию и состояние интерфейса.

        Сессия — ``None``, если диалог в этом чате не запускали или он уже
        завершён; состояние интерфейса в этом случае пустое.
        """
        data = await state.get_data()
        raw = data.get(self.key)
        if raw:
            return self._restore(raw)
        for legacy in self.legacy_keys:
            raw = data.get(legacy)
            if not raw:
                continue
            session, ui = self._restore(raw)
            if session is not None:
                data.pop(legacy)
                data[self.key] = raw
                await state.set_data(data)
                return session, ui
        return None, DialogUIState()

    def _restore(
        self, raw: dict[str, Any]
    ) -> tuple[DialogSession | None, DialogUIState]:
        if self.engine is not None:
            session = self.engine.restore_session(raw["session"])
        else:
            session = DialogSession.from_dict(raw["session"])
        if session is None:
            return None, DialogUIState()
        return session, DialogUIState.from_dict(raw.get("ui", {}))

    async def save(
        self, state: FSMContext, session: DialogSession, ui: DialogUIState
    ) -> None:
        """Сохранить сессию и состояние интерфейса."""
        await state.update_data(
            {self.key: {"session": session.to_dict(), "ui": ui.to_dict()}}
        )

    async def clear(self, state: FSMContext) -> None:
        """Убрать состояние диалога, не трогая остальные данные FSM.

        ``state.clear()`` здесь не годится: в тех же данных бот держит своё, и
        завершение анкеты не повод это стирать.
        """
        data = await state.get_data()
        if self.key in data:
            data.pop(self.key)
            await state.set_data(data)
