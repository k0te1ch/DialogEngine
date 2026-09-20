"""Тесты доставки: протокол DialogSender и реализация по умолчанию."""

from types import SimpleNamespace

import pytest

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

from aiogram.exceptions import TelegramBadRequest  # noqa: E402

DefaultSender = aiogram_integration.DefaultSender
DialogSender = aiogram_integration.DialogSender
MessageAnchor = aiogram_integration.MessageAnchor
StepView = aiogram_integration.StepView

ANCHOR = MessageAnchor(chat_id=42, message_id=100)


class FakeBot:
    """Записывает вызовы вместо похода в Telegram."""

    def __init__(self, edit_error: Exception | None = None):
        self.edit_error = edit_error
        self.sent = []
        self.edited = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return SimpleNamespace(
            chat=SimpleNamespace(id=chat_id), message_id=100 + len(self.sent)
        )

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append({"message_id": message_id, "text": text})
        if self.edit_error is not None:
            raise self.edit_error
        return True


@pytest.mark.asyncio
async def test_first_show_sends_a_message():
    bot = FakeBot()
    sender = DefaultSender(bot, chat_id=42)

    anchor = await sender.show(StepView(text="Выберите предмет"), None)

    assert bot.sent == [{"chat_id": 42, "text": "Выберите предмет"}]
    assert anchor == MessageAnchor(chat_id=42, message_id=101)


@pytest.mark.asyncio
async def test_next_shows_edit_the_same_message():
    bot = FakeBot()
    sender = DefaultSender(bot, chat_id=42)

    anchor = await sender.show(StepView(text="Срок"), ANCHOR)

    assert anchor == ANCHOR
    assert bot.sent == []
    assert bot.edited == [{"message_id": 100, "text": "Срок"}]


@pytest.mark.asyncio
async def test_unchanged_message_is_not_resent():
    bot = FakeBot(TelegramBadRequest(method=None, message="message is not modified"))
    sender = DefaultSender(bot, chat_id=42)

    anchor = await sender.show(StepView(text="Срок"), ANCHOR)

    assert anchor == ANCHOR
    assert bot.sent == []


@pytest.mark.asyncio
async def test_lost_message_is_replaced_with_a_new_one():
    bot = FakeBot(TelegramBadRequest(method=None, message="message to edit not found"))
    sender = DefaultSender(bot, chat_id=42)

    anchor = await sender.show(StepView(text="Срок"), ANCHOR)

    assert len(bot.sent) == 1
    assert anchor == MessageAnchor(chat_id=42, message_id=101)


def test_validation_error_is_rendered_above_the_question():
    sender = DefaultSender(FakeBot(), chat_id=42)

    text = sender.render_text(StepView(text="Возраст?", error="Ожидается число."))

    assert text == "⚠️ Ожидается число.\n\nВозраст?"


def test_default_sender_satisfies_the_protocol():
    assert isinstance(DefaultSender(FakeBot(), chat_id=42), DialogSender)
