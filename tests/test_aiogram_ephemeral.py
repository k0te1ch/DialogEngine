"""Тесты эфемерной доставки."""

from datetime import datetime
from types import SimpleNamespace

import pytest

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

from aiogram.exceptions import TelegramBadRequest  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, User  # noqa: E402

from dialog_engine.exceptions import DialogError  # noqa: E402

DefaultSender = aiogram_integration.DefaultSender
DialogSender = aiogram_integration.DialogSender
EphemeralSender = aiogram_integration.EphemeralSender
MessageAnchor = aiogram_integration.MessageAnchor
StepView = aiogram_integration.StepView
ephemeral_in_groups = aiogram_integration.ephemeral_in_groups

GROUP_ID = -1001
USER_ID = 7
ANCHOR = MessageAnchor(chat_id=GROUP_ID, message_id=5, receiver_user_id=USER_ID)
GROUP = Chat(id=GROUP_ID, type="supergroup")
PRIVATE = Chat(id=USER_ID, type="private")
USER = User(id=USER_ID, is_bot=False, first_name="Алиса")


class FakeBot:
    """Записывает вызовы вместо похода в Telegram."""

    def __init__(self, edit_error: Exception | None = None):
        self.edit_error = edit_error
        self.sent = []
        self.edited = []
        self.plain_edits = []

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return SimpleNamespace(
            chat=SimpleNamespace(id=chat_id),
            message_id=0,
            ephemeral_message_id=10 + len(self.sent),
        )

    async def edit_ephemeral_message_text(self, **kwargs):
        self.edited.append(kwargs)
        if self.edit_error is not None:
            raise self.edit_error
        return True

    async def edit_message_text(self, **kwargs):
        self.plain_edits.append(kwargs)
        return True


def message(chat=GROUP, ephemeral_message_id=None, bot=None):
    return Message(
        message_id=0 if ephemeral_message_id else 1,
        date=datetime.now(),
        chat=chat,
        from_user=USER,
        text="/homework",
        ephemeral_message_id=ephemeral_message_id,
    ).as_(bot)


def callback(origin, bot=None):
    return CallbackQuery(
        id="q1", from_user=USER, chat_instance="ci", message=origin, data="x"
    ).as_(bot)


@pytest.mark.asyncio
async def test_first_show_sends_an_ephemeral_message():
    bot = FakeBot()
    sender = EphemeralSender(bot, GROUP_ID, USER_ID, callback_query_id="q1")

    anchor = await sender.show(StepView(text="Выберите предмет"), None)

    [sent] = bot.sent
    params = sent["ephemeral_message_parameters"]
    assert params.receiver_user_id == USER_ID
    assert params.callback_query_id == "q1"
    assert params.replace_callback_query_message is None
    assert sent["reply_parameters"] is None
    assert anchor == MessageAnchor(
        chat_id=GROUP_ID, message_id=11, receiver_user_id=USER_ID
    )


@pytest.mark.asyncio
async def test_reply_to_an_ephemeral_command():
    bot = FakeBot()
    sender = EphemeralSender(bot, GROUP_ID, USER_ID, reply_to_ephemeral_message_id=3)

    await sender.show(StepView(text="Выберите предмет"), None)

    assert bot.sent[0]["reply_parameters"].ephemeral_message_id == 3


@pytest.mark.asyncio
async def test_next_shows_edit_the_ephemeral_message():
    bot = FakeBot()
    sender = EphemeralSender(bot, GROUP_ID, USER_ID)

    anchor = await sender.show(StepView(text="Срок"), ANCHOR)

    assert anchor == ANCHOR
    assert bot.sent == []
    assert bot.edited == [
        {
            "chat_id": GROUP_ID,
            "receiver_user_id": USER_ID,
            "ephemeral_message_id": 5,
            "text": "Срок",
            "reply_markup": None,
        }
    ]


@pytest.mark.asyncio
async def test_unchanged_message_is_not_resent():
    bot = FakeBot(TelegramBadRequest(method=None, message="message is not modified"))
    sender = EphemeralSender(bot, GROUP_ID, USER_ID)

    assert await sender.show(StepView(text="Срок"), ANCHOR) == ANCHOR
    assert bot.sent == []


@pytest.mark.asyncio
async def test_expired_message_is_replaced_with_a_new_one():
    bot = FakeBot(TelegramBadRequest(method=None, message="message to edit not found"))
    sender = EphemeralSender(bot, GROUP_ID, USER_ID, callback_query_id="q1")

    anchor = await sender.show(StepView(text="Срок"), ANCHOR)

    assert len(bot.sent) == 1
    assert anchor.message_id == 11


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "foreign",
    [
        MessageAnchor(chat_id=GROUP_ID, message_id=5),
        MessageAnchor(chat_id=GROUP_ID, message_id=5, receiver_user_id=8),
    ],
    ids=["plain", "other-receiver"],
)
async def test_foreign_anchor_is_never_edited(foreign):
    bot = FakeBot()
    sender = EphemeralSender(bot, GROUP_ID, USER_ID)

    await sender.show(StepView(text="Срок"), foreign)

    assert bot.edited == []
    assert bot.plain_edits == []
    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_default_sender_does_not_edit_an_ephemeral_anchor():
    bot = FakeBot()

    await DefaultSender(bot, GROUP_ID).show(StepView(text="Срок"), ANCHOR)

    assert bot.plain_edits == []
    assert len(bot.sent) == 1


def test_replace_requires_a_callback_query():
    with pytest.raises(DialogError):
        EphemeralSender(
            FakeBot(), GROUP_ID, USER_ID, replace_callback_query_message=True
        )


def test_for_callback_takes_the_query_id():
    bot = FakeBot()

    sender = EphemeralSender.for_event(
        callback(message(), bot), replace_callback_query_message=True
    )

    assert sender.bot is bot
    assert (sender.chat_id, sender.receiver_user_id) == (GROUP_ID, USER_ID)
    assert sender.callback_query_id == "q1"
    assert sender.replace_callback_query_message is True


def test_replace_is_dropped_for_clicks_in_ephemeral_messages():
    query = callback(message(ephemeral_message_id=5))

    sender = EphemeralSender.for_event(query, replace_callback_query_message=True)

    assert sender.replace_callback_query_message is False


def test_for_ephemeral_command_replies_to_it():
    sender = EphemeralSender.for_event(message(ephemeral_message_id=3))

    assert sender.reply_to_ephemeral_message_id == 3
    assert sender.callback_query_id is None


def test_for_inline_mode_click_is_rejected():
    query = CallbackQuery(id="q1", from_user=USER, chat_instance="ci")

    with pytest.raises(DialogError):
        EphemeralSender.for_event(query)


def test_ephemeral_in_groups_picks_by_chat_type():
    assert isinstance(ephemeral_in_groups(message(GROUP)), EphemeralSender)
    private = ephemeral_in_groups(callback(message(PRIVATE)))
    assert type(private) is DefaultSender
    assert private.chat_id == USER_ID


def test_ephemeral_sender_satisfies_the_protocol():
    assert isinstance(EphemeralSender(FakeBot(), GROUP_ID, USER_ID), DialogSender)


@pytest.mark.parametrize("anchor", [ANCHOR, MessageAnchor(chat_id=42, message_id=1)])
def test_anchor_round_trip(anchor):
    assert MessageAnchor.from_dict(anchor.to_dict()) == anchor


def test_anchor_saved_before_the_ephemeral_field_still_loads():
    anchor = MessageAnchor.from_dict({"chat_id": 42, "message_id": 1})

    assert anchor.is_ephemeral is False
