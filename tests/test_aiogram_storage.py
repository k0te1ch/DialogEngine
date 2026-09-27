"""Тесты сохранения сессии и состояния интерфейса в FSMContext."""

import pytest

from dialog_engine import DialogEngine
from dialog_engine.session import SessionStatus

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.storage.base import StorageKey  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402

DialogUIState = aiogram_integration.DialogUIState
FSMDialogStorage = aiogram_integration.FSMDialogStorage
MessageAnchor = aiogram_integration.MessageAnchor

STEPS = [
    {"id": "name", "type": "text", "text": "Имя"},
    {"id": "age", "type": "number", "text": "Возраст"},
]


@pytest.fixture
def state():
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=42, user_id=7),
    )


@pytest.fixture
def storage():
    return FSMDialogStorage()


@pytest.mark.asyncio
async def test_load_without_a_dialog_returns_nothing(storage, state):
    session, ui = await storage.load(state)

    assert session is None
    assert ui == DialogUIState()


@pytest.mark.asyncio
async def test_session_survives_a_restart(storage, state):
    engine = DialogEngine.from_list(STEPS)
    session = engine.create_session()
    engine.submit(session, "Алиса")
    ui = DialogUIState(page=2, selected=["mon"], anchor=MessageAnchor(42, 100))

    await storage.save(state, session, ui)

    # Новый экземпляр движка и хранилища — как после перезапуска процесса.
    restored_session, restored_ui = await FSMDialogStorage().load(state)

    assert restored_session.answers == {"name": "Алиса"}
    assert DialogEngine.from_list(STEPS).current_step(restored_session).id == "age"
    assert restored_session.status is SessionStatus.IN_PROGRESS
    assert restored_ui == ui


@pytest.mark.asyncio
async def test_clear_keeps_other_fsm_data(storage, state):
    engine = DialogEngine.from_list(STEPS)
    await state.update_data(user_locale="ru")
    await storage.save(state, engine.create_session(), DialogUIState())

    await storage.clear(state)

    assert await state.get_data() == {"user_locale": "ru"}
    session, _ui = await storage.load(state)
    assert session is None


@pytest.mark.asyncio
async def test_custom_key_isolates_two_dialogs(state):
    engine = DialogEngine.from_list(STEPS)
    wizard = FSMDialogStorage(key="wizard")
    survey = FSMDialogStorage(key="survey")

    session = engine.create_session()
    engine.submit(session, "Алиса")
    await wizard.save(state, session, DialogUIState())
    await survey.save(state, engine.create_session(), DialogUIState())

    wizard_session, _ui = await wizard.load(state)
    survey_session, _ui = await survey.load(state)

    assert wizard_session.answers == {"name": "Алиса"}
    assert survey_session.answers == {}


def test_ui_state_roundtrip():
    ui = DialogUIState(page=3, selected=["a", "b"], anchor=MessageAnchor(42, 100))

    assert DialogUIState.from_dict(ui.to_dict()) == ui


def test_ui_state_reset_keeps_the_anchor():
    ui = DialogUIState(page=3, selected=["a"], anchor=MessageAnchor(42, 100))

    ui.reset_step()

    assert ui.page == 0
    assert ui.selected == []
    assert ui.anchor == MessageAnchor(42, 100)


# ── Несколько анкет в одном чате ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_for_engine_keys_by_dialog_and_scope(state):
    upload = DialogEngine.from_list(STEPS, dialog_id="upload")
    assert FSMDialogStorage.for_engine(upload).key == "dialog_engine:upload"
    first = FSMDialogStorage.for_engine(upload, scope=100)
    second = FSMDialogStorage.for_engine(upload, scope=101)
    assert first.key == "dialog_engine:upload:100"

    await first.save(state, upload.create_session(), DialogUIState())
    assert (await second.load(state))[0] is None
    assert (await first.load(state))[0] is not None


@pytest.mark.asyncio
async def test_legacy_key_migrates_own_session(state):
    upload = DialogEngine.from_list(STEPS, dialog_id="upload")
    session = upload.create_session()
    upload.submit(session, "Алиса")
    await FSMDialogStorage().save(state, session, DialogUIState(page=1))

    storage = FSMDialogStorage.for_engine(upload)
    restored, ui = await storage.load(state)
    assert restored.answers == {"name": "Алиса"}
    assert ui.page == 1
    data = await state.get_data()
    assert "dialog_engine" not in data
    assert "dialog_engine:upload" in data


@pytest.mark.asyncio
async def test_legacy_key_with_foreign_session_is_left_alone(state):
    upload = DialogEngine.from_list(STEPS, dialog_id="upload")
    other = DialogEngine.from_list(STEPS, dialog_id="other")
    await FSMDialogStorage().save(state, other.create_session(), DialogUIState())

    assert (await FSMDialogStorage.for_engine(upload).load(state))[0] is None
    assert "dialog_engine" in await state.get_data()


@pytest.mark.asyncio
async def test_foreign_session_under_own_key_is_ignored(state):
    upload = DialogEngine.from_list(STEPS, dialog_id="upload")
    other = DialogEngine.from_list(STEPS, dialog_id="other")
    storage = FSMDialogStorage.for_engine(upload)
    await storage.save(state, other.create_session(), DialogUIState())
    assert (await storage.load(state))[0] is None
