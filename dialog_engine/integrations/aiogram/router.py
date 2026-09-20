"""Тонкая прослойка между апдейтами aiogram и :class:`DialogRunner`.

Здесь живёт всё, что знает про объекты aiogram: фильтры и готовый роутер.
Сам ход анкеты — в :mod:`.runner`, поэтому этот модуль можно не использовать
вовсе и вызывать раннер из собственных хендлеров.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from .callbacks import CallbackParseError, DialogCallback
from .runner import DialogRunner, DialogTurn
from .storage import FSMDialogStorage
from .views import DialogSender

SenderFactory = Callable[[Bot, int | str], DialogSender]
"""Как получить отправителя для конкретного чата."""

CompletionHandler = Callable[[TelegramObject, dict[str, Any]], Awaitable[None]]
"""Что сделать с собранными ответами, когда анкета дошла до конца."""


class DialogCallbackFilter(Filter):
    """Пропускает только кнопки dialog_engine.

    Чужие ``callback_data`` отсеиваются до раннера, чтобы роутер анкеты мог
    спокойно соседствовать с остальными кнопками бота.
    """

    async def __call__(self, query: CallbackQuery) -> bool | dict[str, Any]:
        try:
            callback = DialogCallback.unpack(query.data)
        except CallbackParseError:
            return False
        return {"dialog_callback": callback}


class DialogActiveFilter(Filter):
    """Пропускает апдейт, только если в этом чате идёт анкета.

    Без него хендлер текста перехватывал бы любое сообщение пользователя.
    """

    def __init__(self, storage: FSMDialogStorage | None = None) -> None:
        self.storage = storage or FSMDialogStorage()

    async def __call__(self, _event: TelegramObject, state: FSMContext) -> bool:
        session, _ui = await self.storage.load(state)
        return session is not None and session.is_active


def build_dialog_router(
    runner: DialogRunner,
    sender_factory: SenderFactory,
    *,
    on_complete: CompletionHandler | None = None,
    on_cancel: CompletionHandler | None = None,
    name: str | None = None,
) -> Router:
    """Собрать роутер, ведущий анкету *runner*.

    Роутер обрабатывает нажатия кнопок анкеты и текстовые сообщения, пока
    анкета активна. Запуск анкеты (``runner.start``) остаётся за ботом: он сам
    решает, по какой команде или кнопке она начинается.
    """
    router = Router(name=name or f"dialog:{runner.engine.dialog_id}")

    @router.callback_query(DialogCallbackFilter())
    async def _on_callback(query: CallbackQuery, state: FSMContext) -> None:
        sender = sender_factory(query.bot, query.message.chat.id)
        turn = await runner.on_callback(query.data, state, sender)
        # Telegram держит «часики» на кнопке, пока на запрос не ответили.
        await query.answer(text=turn.alert, show_alert=bool(turn.alert))
        await _notify(turn, query, on_complete, on_cancel)

    @router.message(DialogActiveFilter(runner.storage), F.text)
    async def _on_text(message: Message, state: FSMContext) -> None:
        sender = sender_factory(message.bot, message.chat.id)
        turn = await runner.on_text(message.text or "", state, sender)
        await _notify(turn, message, on_complete, on_cancel)

    return router


async def _notify(
    turn: DialogTurn,
    event: TelegramObject,
    on_complete: CompletionHandler | None,
    on_cancel: CompletionHandler | None,
) -> None:
    if turn.finished and on_complete is not None:
        await on_complete(event, turn.answers)
    elif turn.cancelled and on_cancel is not None:
        await on_cancel(event, {})
