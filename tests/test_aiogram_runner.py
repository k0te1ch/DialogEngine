"""Тесты хода анкеты и сохранения состояния в FSM."""

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
DialogRunner = aiogram_integration.DialogRunner
DialogUIState = aiogram_integration.DialogUIState
FSMDialogStorage = aiogram_integration.FSMDialogStorage
KeyboardLayout = aiogram_integration.KeyboardLayout
MessageAnchor = aiogram_integration.MessageAnchor
build = aiogram_integration.build

LAYOUT = KeyboardLayout(row_width=2, page_size=2)

STEPS = [
    {
        "id": "subject",
        "type": "choice",
        "text": "Выберите предмет",
        "choices": {"math": "Математика", "phys": "Физика", "prog": "Программирование"},
    },
    {"id": "task", "type": "text", "text": "Текст задания", "min": 3},
    {
        "id": "deadline",
        "type": "choice",
        "text": "Срок",
        "choices": {"today": "Сегодня", "tomorrow": "Завтра"},
    },
]


class FakeSender:
    """Собирает показанные представления вместо отправки в Telegram."""

    def __init__(self):
        self.views = []

    async def show(self, view, anchor):
        self.views.append(view)
        return anchor or MessageAnchor(chat_id=42, message_id=100)

    @property
    def last(self):
        return self.views[-1]


@pytest.fixture
def engine():
    return DialogEngine.from_list(STEPS, dialog_id="homework")


@pytest.fixture
def runner(engine):
    return DialogRunner(engine, layout=LAYOUT)


@pytest.fixture
def state():
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=42, user_id=7),
    )


@pytest.fixture
def sender():
    return FakeSender()


def payload(engine, step_id, action, arg=0):
    return build(action, engine.get_step_by_id(step_id), arg)


async def pick(runner, engine, state, sender, step_id, index):
    return await runner.on_callback(
        payload(engine, step_id, DialogAction.PICK, index), state, sender
    )


# ── Прохождение анкеты ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_shows_the_first_step(runner, state, sender):
    await runner.start(state, sender)

    assert sender.last.text == "Выберите предмет"
    assert sender.last.progress == (1, 3)
    assert sender.last.error is None


@pytest.mark.asyncio
async def test_full_run_returns_answers_and_clears_state(runner, engine, state, sender):
    await runner.start(state, sender)
    await pick(runner, engine, state, sender, "subject", 1)
    await runner.on_text("Прочитать главу 3", state, sender)
    turn = await pick(runner, engine, state, sender, "deadline", 0)

    assert turn.finished
    assert turn.answers == {
        "subject": "phys",
        "task": "Прочитать главу 3",
        "deadline": "today",
    }
    assert await state.get_data() == {}


@pytest.mark.asyncio
async def test_one_message_is_redrawn_for_every_step(runner, engine, state, sender):
    await runner.start(state, sender)
    await pick(runner, engine, state, sender, "subject", 0)

    _session, ui = await FSMDialogStorage().load(state)
    assert ui.anchor == MessageAnchor(chat_id=42, message_id=100)
    assert len(sender.views) == 2  # два показа, но привязка одна


# ── Ошибки валидации ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_error_keeps_the_step(runner, engine, state, sender):
    await runner.start(state, sender)
    await pick(runner, engine, state, sender, "subject", 0)

    turn = await runner.on_text("ок", state, sender)

    assert turn.finished is False
    assert sender.last.error == "Слишком короткий текст (минимум 3 символов)."
    assert sender.last.step.id == "task"

    await runner.on_text("Решить задачи 1-5", state, sender)
    assert sender.last.step.id == "deadline"


@pytest.mark.asyncio
async def test_text_on_a_button_step_is_refused(runner, state, sender):
    await runner.start(state, sender)

    await runner.on_text("Математика", state, sender)

    assert sender.last.error == "Выберите вариант с помощью кнопок."
    assert sender.last.step.id == "subject"


# ── Пагинация и устаревшие кнопки ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_switch_does_not_touch_answers(runner, engine, state, sender):
    await runner.start(state, sender)

    await runner.on_callback(
        payload(engine, "subject", DialogAction.PAGE, 1), state, sender
    )

    session, ui = await FSMDialogStorage().load(state)
    assert ui.page == 1
    assert session.answers == {}


@pytest.mark.asyncio
async def test_page_resets_on_the_next_step(runner, engine, state, sender):
    await runner.start(state, sender)
    await runner.on_callback(
        payload(engine, "subject", DialogAction.PAGE, 1), state, sender
    )
    await pick(runner, engine, state, sender, "subject", 2)
    await runner.on_text("Решить задачи 1-5", state, sender)

    _session, ui = await FSMDialogStorage().load(state)
    assert ui.page == 0


@pytest.mark.asyncio
async def test_button_from_a_previous_step_is_rejected(runner, engine, state, sender):
    await runner.start(state, sender)
    await pick(runner, engine, state, sender, "subject", 0)

    turn = await pick(runner, engine, state, sender, "subject", 1)

    assert turn.alert == aiogram_integration.runner.STALE_BUTTON_ALERT
    session, _ui = await FSMDialogStorage().load(state)
    assert session.answers == {"subject": "math"}


@pytest.mark.asyncio
async def test_noop_button_changes_nothing(runner, engine, state, sender):
    await runner.start(state, sender)

    turn = await runner.on_callback(
        payload(engine, "subject", DialogAction.NOOP, 0), state, sender
    )

    assert turn.alert is None
    assert len(sender.views) == 1


@pytest.mark.asyncio
async def test_option_index_out_of_range_is_rejected(runner, engine, state, sender):
    await runner.start(state, sender)

    turn = await pick(runner, engine, state, sender, "subject", 99)

    assert turn.alert == aiogram_integration.runner.STALE_BUTTON_ALERT


@pytest.mark.asyncio
async def test_foreign_callback_is_not_handled(runner, state, sender):
    turn = await runner.on_callback("other_bot:menu", state, sender)

    assert turn.handled is False


@pytest.mark.asyncio
async def test_callback_without_a_session_is_not_handled(runner, engine, state, sender):
    turn = await runner.on_callback(
        payload(engine, "subject", DialogAction.PICK, 0), state, sender
    )

    assert turn.handled is False


# ── Навигация ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_back_returns_to_the_previous_step_and_erases_its_answer(
    runner, engine, state, sender
):
    await runner.start(state, sender)
    await pick(runner, engine, state, sender, "subject", 0)

    await runner.on_callback(payload(engine, "task", DialogAction.BACK), state, sender)

    session, _ui = await FSMDialogStorage().load(state)
    assert sender.last.step.id == "subject"
    assert session.answers == {}  # движок стирает ответ шага, на который вернулись


@pytest.mark.asyncio
async def test_back_on_the_first_step_only_warns(runner, engine, state, sender):
    await runner.start(state, sender)

    turn = await runner.on_callback(
        payload(engine, "subject", DialogAction.BACK), state, sender
    )

    assert turn.alert == "Already on the first step."
    assert len(sender.views) == 1


@pytest.mark.asyncio
async def test_skip_is_refused_on_a_required_step(runner, engine, state, sender):
    await runner.start(state, sender)

    turn = await runner.on_callback(
        payload(engine, "subject", DialogAction.SKIP), state, sender
    )

    assert turn.alert is not None
    session, _ui = await FSMDialogStorage().load(state)
    assert session.answers == {}


@pytest.mark.asyncio
async def test_cancel_drops_the_session(runner, engine, state, sender):
    await runner.start(state, sender)

    turn = await runner.on_callback(
        payload(engine, "subject", DialogAction.CANCEL), state, sender
    )

    assert turn.cancelled
    assert await state.get_data() == {}


# ── Несколько вариантов ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_choice_collects_selection_outside_of_answers(state, sender):
    engine = DialogEngine.from_list(
        [
            {
                "id": "days",
                "type": "multi_choice",
                "text": "Дни",
                "choices": {"mon": "Пн", "tue": "Вт", "wed": "Ср"},
                "min": 1,
            }
        ],
        dialog_id="schedule",
    )
    runner = DialogRunner(engine, layout=LAYOUT)
    await runner.start(state, sender)

    await runner.on_callback(
        build(DialogAction.PICK, engine.steps[0], 0), state, sender
    )
    await runner.on_callback(
        build(DialogAction.PICK, engine.steps[0], 2), state, sender
    )
    session, ui = await FSMDialogStorage().load(state)

    assert ui.selected == ["mon", "wed"]
    assert session.answers == {}

    turn = await runner.on_callback(
        build(DialogAction.DONE, engine.steps[0]), state, sender
    )
    assert turn.finished
    assert turn.answers == {"days": ["mon", "wed"]}


@pytest.mark.asyncio
async def test_multi_choice_pick_toggles_off(state, sender):
    engine = DialogEngine.from_list(
        [
            {
                "id": "days",
                "type": "multi_choice",
                "text": "Дни",
                "choices": {"mon": "Пн", "tue": "Вт"},
            }
        ],
        dialog_id="schedule",
    )
    runner = DialogRunner(engine, layout=LAYOUT)
    await runner.start(state, sender)

    await runner.on_callback(
        build(DialogAction.PICK, engine.steps[0], 0), state, sender
    )
    await runner.on_callback(
        build(DialogAction.PICK, engine.steps[0], 0), state, sender
    )

    _session, ui = await FSMDialogStorage().load(state)
    assert ui.selected == []


# ── Произвольные значения ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_value_answers_a_media_step(state, sender):
    engine = DialogEngine.from_list(
        [{"id": "photos", "type": "photo", "text": "Фото", "min": 1}],
        dialog_id="media",
    )
    runner = DialogRunner(engine)
    await runner.start(state, sender)

    turn = await runner.submit_value(["file_id_1"], state, sender)

    assert turn.answers == {"photos": ["file_id_1"]}
