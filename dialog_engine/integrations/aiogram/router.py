"""Тонкая прослойка между апдейтами aiogram и :class:`DialogRunner`.

Здесь живёт всё, что знает про объекты aiogram: фильтры и готовый роутер.
Сам ход анкеты — в :mod:`.runner`, поэтому этот модуль можно не использовать
вовсе и вызывать раннер из собственных хендлеров.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from .callbacks import CallbackParseError, DialogCallback
from .runner import DialogRunner, DialogTurn
from .storage import FSMDialogStorage
from .views import DialogSender

SenderFactory = Callable[[Bot, int | str], DialogSender]
"""Как получить отправителя для конкретного чата."""

EventSenderFactory = Callable[[CallbackQuery | Message], DialogSender]
"""Как получить отправителя из апдейта — когда чата мало, например для
эфемерных сообщений, которым нужны получатель и ``callback_query_id``."""

logger = logging.getLogger(__name__)


class TextAnswerPolicy(StrEnum):
    """Что делать с сообщением, которым пользователь ответил на шаг текстом.

    Ответ, отправленный как reply на эфемерное сообщение, сам эфемерный:
    его не видит ни группа, ни кто-либо, кроме бота, и удалять там нечего —
    такие ответы не трогаются ни при какой политике (клиент принуждает к
    reply, если у клавиатуры включён ``KeyboardLayout.force_reply``). Политика
    касается обычных сообщений: их читает вся группа. Чтобы удалять, боту
    нужно право администратора ``can_delete_messages``.
    """

    KEEP = "keep"
    """Оставить как есть."""

    DELETE = "delete"
    """Удалять в любом чате, включая личный."""

    DELETE_IN_GROUPS = "delete_in_groups"
    """Удалять в группах и супергруппах, в личке оставлять."""


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
    sender_factory: SenderFactory | None = None,
    *,
    event_sender_factory: EventSenderFactory | None = None,
    on_complete: CompletionHandler | None = None,
    on_cancel: CompletionHandler | None = None,
    text_answers: TextAnswerPolicy = TextAnswerPolicy.KEEP,
    name: str | None = None,
) -> Router:
    """Собрать роутер, ведущий анкету *runner*.

    Роутер обрабатывает нажатия кнопок анкеты и текстовые сообщения, пока
    анкета активна. Запуск анкеты (``runner.start``) остаётся за ботом: он сам
    решает, по какой команде или кнопке она начинается.

    Отправителя задаёт ровно одна из фабрик: *sender_factory* получает бота и
    чат, *event_sender_factory* — сам апдейт (см.
    :meth:`~.ephemeral.EphemeralSender.for_event`).

    *text_answers* решает судьбу текстовых ответов пользователя — см.
    :class:`TextAnswerPolicy`. Удаление идёт после обработки ответа, поэтому
    ответ не теряется, даже если удалить сообщение не удалось.

    Raises:
        ValueError: не передано ни одной фабрики или переданы обе.
    """
    if (sender_factory is None) == (event_sender_factory is None):
        raise ValueError(
            "Передайте ровно одно из sender_factory и event_sender_factory."
        )
    make_sender = event_sender_factory or _chat_sender_factory(sender_factory)
    router = Router(name=name or f"dialog:{runner.engine.dialog_id}")

    @router.callback_query(DialogCallbackFilter())
    async def _on_callback(query: CallbackQuery, state: FSMContext) -> None:
        sender = make_sender(query)
        turn = await runner.on_callback(query.data, state, sender)
        # Telegram держит «часики» на кнопке, пока на запрос не ответили.
        await query.answer(text=turn.alert, show_alert=bool(turn.alert))
        await _notify(turn, query, on_complete, on_cancel)

    @router.message(DialogActiveFilter(runner.storage), F.text)
    async def _on_text(message: Message, state: FSMContext) -> None:
        sender = make_sender(message)
        turn = await runner.on_text(message.text or "", state, sender)
        if _should_delete(text_answers, message):
            await _delete_answer(message)
        await _notify(turn, message, on_complete, on_cancel)

    return router


def _chat_sender_factory(factory: SenderFactory) -> EventSenderFactory:
    def make(event: CallbackQuery | Message) -> DialogSender:
        message = event.message if isinstance(event, CallbackQuery) else event
        return factory(event.bot, message.chat.id)

    return make


def _should_delete(policy: TextAnswerPolicy, message: Message) -> bool:
    if message.ephemeral_message_id is not None:
        # Эфемерный ответ и так не виден группе, а deleteMessage его не берёт.
        return False
    if policy is TextAnswerPolicy.DELETE_IN_GROUPS:
        return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    return policy is TextAnswerPolicy.DELETE


async def _delete_answer(message: Message) -> None:
    """Удалить ответ пользователя; без прав на это анкета не должна падать."""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.warning(
            "Не удалось удалить ответ %s в чате %s: %s",
            message.message_id,
            message.chat.id,
            exc,
        )


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
