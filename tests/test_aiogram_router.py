"""Тесты фильтров и сборки роутера."""

from types import SimpleNamespace

import pytest

from dialog_engine import DialogEngine

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

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
