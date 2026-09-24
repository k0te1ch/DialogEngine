"""Доставка шагов эфемерными сообщениями (Bot API 10.3).

Эфемерное сообщение в группе видит только его получатель: анкета не засоряет
общий чат и не показывает ответы остальным участникам. Отличия от обычного
сообщения, из-за которых нужен отдельный отправитель:

* адресат задаётся явно — ``EphemeralMessageParameters.receiver_user_id``;
* ``message_id`` у такого сообщения всегда ``0``, адресуется оно парой
  «получатель + ``ephemeral_message_id``», а правится
  ``editEphemeralMessageText``;
* бот без прав администратора может отправить эфемерное сообщение только в
  ответ на действие пользователя не старше 15 секунд: нажатие кнопки
  (``callback_query_id``) или эфемерную команду
  (``reply_parameters.ephemeral_message_id``). Администратор может писать
  любому участнику в любой момент. Правку это окно не ограничивает: шаги
  перерисовываются, сколько бы пользователь ни заполнял анкету.

Ответ пользователя на эфемерное сообщение сам эфемерный, поэтому диалог
целиком может остаться невидимым для группы: объявите команду входа с
``is_ephemeral`` в ``setMyCommands`` и включите
``KeyboardLayout(force_reply=True)``.

Поэтому отправителя удобнее собирать из апдейта — см.
:meth:`EphemeralSender.for_event` и параметр ``event_sender_factory`` у
:func:`~.router.build_dialog_router`.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import (
    CallbackQuery,
    EphemeralMessageParameters,
    InlineKeyboardMarkup,
    Message,
    ReplyParameters,
)

from dialog_engine.exceptions import DialogError

from .views import DefaultSender, DialogSender, MessageAnchor


class EphemeralSender(DefaultSender):
    """Показывает анкету эфемерным сообщением одному участнику группы.

    Как и :class:`DefaultSender`, отправляет сообщение один раз и дальше
    правит его. Если правка не удалась (эфемерные сообщения пропадают после
    перезапуска клиента или по истечении времени), присылает новое — для этого
    у бота должно быть право отправки: свежий ``callback_query_id``, эфемерная
    команда или права администратора.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int | str,
        receiver_user_id: int,
        *,
        callback_query_id: str | None = None,
        reply_to_ephemeral_message_id: int | None = None,
        replace_callback_query_message: bool = False,
    ) -> None:
        """
        Args:
            receiver_user_id: кому показывать анкету.
            callback_query_id: нажатие, в ответ на которое идёт отправка.
            reply_to_ephemeral_message_id: эфемерная команда пользователя, на
                которую отвечает бот.
            replace_callback_query_message: показать анкету вместо сообщения,
                на кнопку которого нажали. Только вместе с
                ``callback_query_id`` и не для нажатий в эфемерных сообщениях.
        """
        super().__init__(bot, chat_id)
        if replace_callback_query_message and callback_query_id is None:
            raise DialogError(
                "replace_callback_query_message требует callback_query_id."
            )
        self.receiver_user_id = receiver_user_id
        self.callback_query_id = callback_query_id
        self.reply_to_ephemeral_message_id = reply_to_ephemeral_message_id
        self.replace_callback_query_message = replace_callback_query_message

    @classmethod
    def for_event(
        cls,
        event: CallbackQuery | Message,
        *,
        replace_callback_query_message: bool = False,
    ) -> EphemeralSender:
        """Собрать отправителя из апдейта, на который отвечает бот.

        Для нажатия берётся ``callback_query_id``, для эфемерной команды —
        её ``ephemeral_message_id``. Замена исходного сообщения молча
        отключается для нажатий в эфемерных сообщениях: Telegram такое
        запрещает, а правка там и так идёт на месте.

        Raises:
            DialogError: у апдейта нет чата (кнопка inline-режима) или
                отправителя.
        """
        if event.from_user is None:
            raise DialogError("Эфемерному сообщению нужен получатель.")
        if isinstance(event, CallbackQuery):
            message = event.message
            if message is None:
                raise DialogError("Нажатие без сообщения: чат неизвестен.")
            from_ephemeral = getattr(message, "ephemeral_message_id", None) is not None
            return cls(
                event.bot,
                message.chat.id,
                event.from_user.id,
                callback_query_id=event.id,
                replace_callback_query_message=(
                    replace_callback_query_message and not from_ephemeral
                ),
            )
        return cls(
            event.bot,
            event.chat.id,
            event.from_user.id,
            reply_to_ephemeral_message_id=event.ephemeral_message_id,
        )

    def _can_edit(self, anchor: MessageAnchor) -> bool:
        # Обычное сообщение или чужое эфемерное не правим: анкета должна
        # остаться видна только своему получателю.
        return anchor.receiver_user_id == self.receiver_user_id

    async def _edit(
        self,
        anchor: MessageAnchor,
        text: str,
        keyboard: InlineKeyboardMarkup | None,
    ) -> None:
        await self.bot.edit_ephemeral_message_text(
            chat_id=anchor.chat_id,
            receiver_user_id=self.receiver_user_id,
            ephemeral_message_id=anchor.message_id,
            text=text,
            reply_markup=keyboard,
        )

    async def _send(
        self, text: str, keyboard: InlineKeyboardMarkup | None
    ) -> MessageAnchor:
        reply = (
            ReplyParameters(ephemeral_message_id=self.reply_to_ephemeral_message_id)
            if self.reply_to_ephemeral_message_id is not None
            else None
        )
        message = await self.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            reply_markup=keyboard,
            reply_parameters=reply,
            ephemeral_message_parameters=EphemeralMessageParameters(
                receiver_user_id=self.receiver_user_id,
                callback_query_id=self.callback_query_id,
                replace_callback_query_message=(
                    self.replace_callback_query_message or None
                ),
            ),
        )
        if message.ephemeral_message_id is None:
            raise DialogError("Telegram не вернул ephemeral_message_id.")
        return MessageAnchor(
            chat_id=message.chat.id,
            message_id=message.ephemeral_message_id,
            receiver_user_id=self.receiver_user_id,
        )


def ephemeral_in_groups(event: CallbackQuery | Message) -> DialogSender:
    """Эфемерно в группах, обычными сообщениями в личке.

    Эфемерные сообщения бывают только в группах и супергруппах, а в личном
    чате их и так никто, кроме собеседника, не видит. Подходит как
    ``event_sender_factory`` для роутера, если анкету запускают и там и там.
    """
    message = event.message if isinstance(event, CallbackQuery) else event
    if message is None:
        raise DialogError("Нажатие без сообщения: чат неизвестен.")
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        return EphemeralSender.for_event(event)
    return DefaultSender(event.bot, message.chat.id)
