"""Что показать пользователю и как это доставить.

Библиотека не отправляет сообщения сама. Причина практическая: бот-потребитель
может отвечать не обычным ``sendMessage``, а ``sendRichMessage`` с
``RichBlockTable`` (Bot API 10.1) и эфемерно в группе
(``ephemeral_message_parameters``, Bot API 10.2, требует прав администратора
чата). У эфемерных сообщений и правка своя — ``editEphemeralMessageText``.
Зашить отправку внутрь значило бы закрыть потребителю все эти пути, поэтому
здесь описан только протокол :class:`DialogSender`, а конкретная доставка —
дело потребителя. :class:`DefaultSender` — рабочая реализация на обычных
сообщениях, которую предполагается заменять, а не дорабатывать; эфемерная
доставка — в :mod:`.ephemeral`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from dialog_engine.step import DialogStep


@dataclass(frozen=True, slots=True)
class MessageAnchor:
    """Сообщение, в котором сейчас нарисован диалог.

    Хранится вместе с сессией, а не в памяти процесса: после перезапуска бота
    шаги обязаны продолжать перерисовывать то же сообщение.
    """

    chat_id: int | str
    message_id: int
    """Для эфемерного сообщения — ``ephemeral_message_id``: его ``message_id``
    в Telegram всегда ``0``."""

    receiver_user_id: int | None = None
    """Получатель эфемерного сообщения; ``None`` — сообщение обычное."""

    @property
    def is_ephemeral(self) -> bool:
        return self.receiver_user_id is not None

    def to_dict(self) -> dict[str, int | str]:
        data: dict[str, int | str] = {
            "chat_id": self.chat_id,
            "message_id": self.message_id,
        }
        if self.receiver_user_id is not None:
            data["receiver_user_id"] = self.receiver_user_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, int | str]) -> MessageAnchor:
        receiver = data.get("receiver_user_id")
        return cls(
            chat_id=data["chat_id"],
            message_id=int(data["message_id"]),
            receiver_user_id=int(receiver) if receiver is not None else None,
        )


@dataclass(frozen=True, slots=True)
class StepView:
    """Готовое представление шага: что спросить и чем ответить.

    Форматирование текста ошибки оставлено получателю: в обычном сообщении это
    строка сверху, а в ``RichBlockTable`` — отдельный блок.
    """

    text: str
    """Текст вопроса, уже прошедший через ``text_resolver``."""

    keyboard: InlineKeyboardMarkup | None = None
    step: DialogStep | None = None
    """Сам шаг — чтобы получатель мог посмотреть ``step.meta`` и тип."""

    error: str | None = None
    """Текст ошибки валидации, если предыдущий ответ не подошёл."""

    progress: tuple[int, int] = (0, 0)
    """``(номер шага, всего шагов)`` — на случай, если бот их показывает."""


@runtime_checkable
class DialogSender(Protocol):
    """Доставка представления шага пользователю.

    Реализация решает сама, отправить новое сообщение или отредактировать
    существующее; ``anchor`` — то, что она вернула в прошлый раз (``None`` на
    первом показе).
    """

    async def show(
        self, view: StepView, anchor: MessageAnchor | None
    ) -> MessageAnchor | None:
        """Показать шаг и вернуть привязку к нарисованному сообщению."""
        ...


class DefaultSender:
    """Отправка обычными сообщениями: первый показ — ``send_message``,
    последующие — ``edit_message_text``.

    Правка вместо новых сообщений нужна, чтобы анкета не растягивала чат на
    десяток сообщений.
    """

    def __init__(self, bot: Bot, chat_id: int | str) -> None:
        self.bot = bot
        self.chat_id = chat_id

    def render_text(self, view: StepView) -> str:
        """Склеить ошибку и вопрос в один текст."""
        if view.error:
            return f"⚠️ {view.error}\n\n{view.text}"
        return view.text

    async def show(
        self, view: StepView, anchor: MessageAnchor | None
    ) -> MessageAnchor | None:
        text = self.render_text(view)
        if anchor is not None and self._can_edit(anchor):
            edited = await self._try_edit(anchor, text, view.keyboard)
            if edited:
                return anchor
            # Сообщение могли удалить или оно стало слишком старым для правки —
            # тогда единственный способ не потерять диалог — прислать новое.
        return await self._send(text, view.keyboard)

    def _can_edit(self, anchor: MessageAnchor) -> bool:
        """Можно ли править *anchor* этим способом доставки.

        У эфемерного якоря ``message_id`` — это ``ephemeral_message_id``, и
        ``edit_message_text`` с ним попал бы в чужое обычное сообщение.
        """
        return not anchor.is_ephemeral

    async def _send(
        self, text: str, keyboard: InlineKeyboardMarkup | None
    ) -> MessageAnchor:
        message = await self.bot.send_message(
            chat_id=self.chat_id, text=text, reply_markup=keyboard
        )
        return MessageAnchor(chat_id=message.chat.id, message_id=message.message_id)

    async def _try_edit(
        self,
        anchor: MessageAnchor,
        text: str,
        keyboard: InlineKeyboardMarkup | None,
    ) -> bool:
        try:
            await self._edit(anchor, text, keyboard)
        except TelegramBadRequest as exc:
            # «message is not modified» означает, что на экране уже нужное
            # состояние: повторная отрисовка той же страницы — не ошибка.
            return "message is not modified" in str(exc)
        return True

    async def _edit(
        self,
        anchor: MessageAnchor,
        text: str,
        keyboard: InlineKeyboardMarkup | None,
    ) -> None:
        await self.bot.edit_message_text(
            chat_id=anchor.chat_id,
            message_id=anchor.message_id,
            text=text,
            reply_markup=keyboard,
        )
