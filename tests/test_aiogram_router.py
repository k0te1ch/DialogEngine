"""Тесты фильтров и сборки роутера."""

from types import SimpleNamespace

import pytest

from dialog_engine import DialogEngine

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

from aiogram.exceptions import TelegramBadRequest  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

DialogAction = aiogram_integration.DialogAction
DialogActiveFilter = aiogram_integration.DialogActiveFilter
DialogCallback = aiogram_integration.DialogCallback
DialogCallbackFilter = aiogram_integration.DialogCallbackFilter
DialogRunner = aiogram_integration.DialogRunner
DialogUIState = aiogram_integration.DialogUIState
FSMDialogStorage = aiogram_integration.FSMDialogStorage
MessageAnchor = aiogram_integration.MessageAnchor
TextAnswerPolicy = aiogram_integration.TextAnswerPolicy
build_dialog_router = aiogram_integration.build_dialog_router
step_token = aiogram_integration.step_token

STEPS = [{"id": "name", "type": "text", "text": "Имя"}]


class FakeSender:
    async def show(self, view, anchor):
        return anchor or MessageAnchor(chat_id=42, message_id=100)


@pytest.fixture
def state():
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=42, user_id=7),
    )


@pytest.mark.asyncio
async def test_callback_filter_passes_parsed_callback():
    payload = DialogCallback(DialogAction.PICK, step_token("name"), 2).pack()

    result = await DialogCallbackFilter()(SimpleNamespace(data=payload))

    assert result == {"dialog_callback": DialogCallback.unpack(payload)}


@pytest.mark.asyncio
async def test_callback_filter_ignores_foreign_buttons():
    assert await DialogCallbackFilter()(SimpleNamespace(data="menu:open")) is False


@pytest.mark.asyncio
async def test_active_filter_is_false_without_a_dialog(state):
    assert await DialogActiveFilter()(SimpleNamespace(), state) is False


@pytest.mark.asyncio
async def test_active_filter_is_true_while_the_dialog_runs(state):
    runner = DialogRunner(DialogEngine.from_list(STEPS))
    await runner.start(state, FakeSender())

    assert await DialogActiveFilter(runner.storage)(SimpleNamespace(), state) is True


@pytest.mark.asyncio
async def test_active_filter_is_false_after_completion(state):
    runner = DialogRunner(DialogEngine.from_list(STEPS))
    sender = FakeSender()
    await runner.start(state, sender)
    await runner.on_text("Алиса", state, sender)

    assert await DialogActiveFilter(runner.storage)(SimpleNamespace(), state) is False


@pytest.mark.asyncio
async def test_active_filter_respects_a_custom_storage_key(state):
    storage = FSMDialogStorage(key="wizard")
    engine = DialogEngine.from_list(STEPS)
    await storage.save(state, engine.create_session(), DialogUIState())

    assert await DialogActiveFilter(storage)(SimpleNamespace(), state) is True
    assert await DialogActiveFilter()(SimpleNamespace(), state) is False


def test_router_is_named_after_the_dialog():
    runner = DialogRunner(DialogEngine.from_list(STEPS, dialog_id="homework"))

    router = build_dialog_router(
        runner, sender_factory=lambda bot, chat_id: FakeSender()
    )

    assert router.name == "dialog:homework"
    assert len(router.callback_query.handlers) == 1
    assert len(router.message.handlers) == 1


def test_router_accepts_an_event_sender_factory():
    runner = DialogRunner(DialogEngine.from_list(STEPS))

    router = build_dialog_router(runner, event_sender_factory=lambda event: None)

    assert len(router.callback_query.handlers) == 1


@pytest.mark.parametrize(
    "factories",
    [{}, {"sender_factory": object(), "event_sender_factory": object()}],
    ids=["none", "both"],
)
def test_router_needs_exactly_one_sender_factory(factories):
    runner = DialogRunner(DialogEngine.from_list(STEPS))

    with pytest.raises(ValueError):
        build_dialog_router(runner, **factories)


class FakeAnswer:
    """Текстовый ответ пользователя, который умеет «удаляться»."""

    def __init__(
        self, text, chat_type="supergroup", delete_error=None, ephemeral=False
    ):
        self.text = text
        self.message_id = 0 if ephemeral else 55
        self.ephemeral_message_id = 777 if ephemeral else None
        self.chat = SimpleNamespace(id=42, type=chat_type)
        self.bot = None
        self.delete_error = delete_error
        self.deleted = False

    async def delete(self):
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted = True


async def answer_text(state, policy, message):
    runner = DialogRunner(DialogEngine.from_list(STEPS))
    completed = []

    async def on_complete(event, answers):
        completed.append(answers)

    router = build_dialog_router(
        runner,
        event_sender_factory=lambda event: FakeSender(),
        on_complete=on_complete,
        text_answers=policy,
    )
    await runner.start(state, FakeSender())
    await router.message.handlers[0].callback(message, state)
    return completed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "chat_type", "deleted"),
    [
        (TextAnswerPolicy.KEEP, "supergroup", False),
        (TextAnswerPolicy.DELETE, "supergroup", True),
        (TextAnswerPolicy.DELETE, "private", True),
        (TextAnswerPolicy.DELETE_IN_GROUPS, "group", True),
        (TextAnswerPolicy.DELETE_IN_GROUPS, "private", False),
    ],
)
async def test_text_answer_policy(state, policy, chat_type, deleted):
    message = FakeAnswer("Алиса", chat_type)

    completed = await answer_text(state, policy, message)

    assert message.deleted is deleted
    assert completed == [{"name": "Алиса"}]


@pytest.mark.asyncio
async def test_failed_deletion_does_not_lose_the_answer(state, caplog):
    error = TelegramBadRequest(method=None, message="message can't be deleted")
    message = FakeAnswer("Алиса", delete_error=error)

    completed = await answer_text(state, TextAnswerPolicy.DELETE, message)

    assert completed == [{"name": "Алиса"}]
    assert "Не удалось удалить ответ" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy", [TextAnswerPolicy.DELETE, TextAnswerPolicy.DELETE_IN_GROUPS]
)
async def test_ephemeral_answers_are_left_alone(state, policy):
    """Эфемерный ответ не виден группе, и deleteMessage его всё равно не берёт."""
    message = FakeAnswer("Алиса", ephemeral=True)

    completed = await answer_text(state, policy, message)

    assert message.deleted is False
    assert completed == [{"name": "Алиса"}]
