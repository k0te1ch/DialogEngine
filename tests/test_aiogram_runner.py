"""Тесты хода анкеты и сохранения состояния в FSM."""

import pytest

from dialog_engine import DialogEngine, FileInfo, ValidationError

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

    _session, ui = await runner.storage.load(state)
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

    session, ui = await runner.storage.load(state)
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

    _session, ui = await runner.storage.load(state)
    assert ui.page == 0


@pytest.mark.asyncio
async def test_button_from_a_previous_step_is_rejected(runner, engine, state, sender):
    await runner.start(state, sender)
    await pick(runner, engine, state, sender, "subject", 0)

    turn = await pick(runner, engine, state, sender, "subject", 1)

    assert turn.alert == aiogram_integration.runner.STALE_BUTTON_ALERT
    session, _ui = await runner.storage.load(state)
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

    session, _ui = await runner.storage.load(state)
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
    session, _ui = await runner.storage.load(state)
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
    session, ui = await runner.storage.load(state)

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

    _session, ui = await runner.storage.load(state)
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


# ── Контекст и валидатор шага ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_with_context_and_step_validator_error(state, sender):
    def check(value, ctx):
        if value != ctx.context["expected"]:
            raise ValidationError("wrong", ctx.step.id)
        ctx.context["checked"] = True

    engine = DialogEngine.from_list(
        STEPS,
        dialog_id="homework",
        validators={"task": check},
        text_resolver=lambda key, answers, context: (
            f"[{context['lang']}] {key}" if key == "Выберите предмет" else key
        ),
    )
    runner = DialogRunner(engine, layout=LAYOUT)
    await runner.start(state, sender, context={"lang": "en", "expected": "abcd"})
    assert sender.last.text == "[en] Выберите предмет"

    await runner.submit_value("math", state, sender)
    await runner.on_text("wxyz", state, sender)
    assert sender.last.error == "wrong"
    assert sender.last.step.id == "task"

    await runner.on_text("abcd", state, sender)
    turn = await runner.submit_value("today", state, sender)
    assert turn.finished
    assert turn.context == {"lang": "en", "expected": "abcd", "checked": True}


# ── Перевод подписей и ошибок ────────────────────────────────────────────────

EN_LABELS = {
    "Математика": "Math",
    "Физика": "Physics",
    "Программирование": "Coding",
    "de.button.back": "Back",
    "de.button.yes": "Yes",
    "de.button.no": "No",
    "de.error.text.min": "At least {min} characters",
    "de.error.button_required": "Use the buttons",
}


def _en(key, answers, context):
    return EN_LABELS.get(key, key) if context.get("lang") == "en" else key


def _texts(view):
    return [b.text for row in view.keyboard.inline_keyboard for b in row]


@pytest.mark.asyncio
async def test_labels_and_errors_translated(state, sender):
    steps = [*STEPS, {"id": "ok", "type": "boolean", "text": "Ok?"}]
    engine = DialogEngine.from_list(steps, dialog_id="homework", text_resolver=_en)
    runner = DialogRunner(engine, layout=LAYOUT)
    await runner.start(state, sender, context={"lang": "en"})
    assert _texts(sender.last)[:2] == ["Math", "Physics"]

    await runner.submit_value("math", state, sender)
    await runner.on_text("ab", state, sender)
    assert sender.last.error == "At least 3 characters"
    assert "Back" in _texts(sender.last)

    await runner.on_text("abcd", state, sender)
    await runner.submit_value("today", state, sender)
    assert _texts(sender.last)[:2] == ["Yes", "No"]
    await runner.on_text("yes", state, sender)
    assert sender.last.error == "Use the buttons"


@pytest.mark.asyncio
async def test_without_translation_labels_unchanged(runner, state, sender):
    await runner.start(state, sender)
    assert _texts(sender.last)[:2] == ["Математика", "Физика"]
    await runner.submit_value("math", state, sender)
    await runner.on_text("ab", state, sender)
    assert sender.last.error == "Слишком короткий текст (минимум 3 символов)."
    assert LAYOUT.back_text in _texts(sender.last)


# ── Две анкеты в одном чате ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_dialogs_in_one_chat(runner, state, sender):
    confirm_engine = DialogEngine.from_list(
        [{"id": "ok", "type": "choice", "text": "Переслать?", "choices": {"y": "Да"}}],
        dialog_id="confirm",
    )
    confirm = DialogRunner(confirm_engine, layout=LAYOUT)
    other_sender = FakeSender()

    await runner.start(state, sender)
    await confirm.start(state, other_sender)

    homework_button = sender.last.keyboard.inline_keyboard[0][0].callback_data
    confirm_button = other_sender.last.keyboard.inline_keyboard[0][0].callback_data

    # Чужая кнопка не обрабатывается и не трогает свою анкету.
    assert (
        await confirm.on_callback(homework_button, state, other_sender)
    ).handled is False
    assert (await runner.on_callback(confirm_button, state, sender)).handled is False

    turn = await confirm.on_callback(confirm_button, state, other_sender)
    assert turn.finished and turn.answers == {"ok": "y"}

    await runner.on_callback(homework_button, state, sender)
    session, _ui = await runner.storage.load(state)
    assert session.answers == {"subject": "math"}


# ── Файлы ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_files_checks_constraints(state, sender):
    engine = DialogEngine.from_list(
        [
            {"id": "mp3", "type": "file", "text": "MP3", "mime_types": ["audio/mpeg"]},
            {"id": "title", "type": "text", "text": "Название"},
        ],
        dialog_id="upload",
    )
    runner = DialogRunner(engine, layout=LAYOUT)
    await runner.start(state, sender)

    await runner.on_text("просто текст", state, sender)
    assert sender.last.error == "Отправьте файл."

    await runner.on_files([FileInfo("v", "video/mp4")], state, sender)
    assert sender.last.error.startswith("Неподходящий тип файла")

    await runner.on_files([FileInfo("a", "audio/mpeg", "a.mp3", 5)], state, sender)
    assert sender.last.step.id == "title"

    await runner.on_files([FileInfo("x", "audio/mpeg")], state, sender)
    assert sender.last.error == "Здесь нужен ответ текстом или кнопкой."

    turn = await runner.on_text("Выпуск", state, sender)
    assert turn.answers["mp3"] == [
        {
            "file_id": "a",
            "mime_type": "audio/mpeg",
            "file_name": "a.mp3",
            "file_size": 5,
        }
    ]


# ── «Назад» с прежним ответом ────────────────────────────────────────────────


def _buttons(view):
    return [
        (b.text, b.callback_data) for row in view.keyboard.inline_keyboard for b in row
    ]


@pytest.mark.asyncio
async def test_back_offers_to_keep_previous_answer(runner, engine, state, sender):
    await runner.start(state, sender)
    await runner.on_callback(
        payload(engine, "subject", DialogAction.PICK, 1), state, sender
    )
    await runner.on_text("Задача", state, sender)
    await runner.on_callback(
        payload(engine, "deadline", DialogAction.BACK), state, sender
    )

    # Текстовый шаг: прежний ответ виден на кнопке.
    keep = [b for b in _buttons(sender.last) if b[0].startswith("Оставить")]
    assert keep[0][0] == "Оставить: Задача"
    await runner.on_callback(keep[0][1], state, sender)
    assert sender.last.step.id == "deadline"

    await runner.on_callback(
        payload(engine, "deadline", DialogAction.BACK), state, sender
    )
    await runner.on_callback(payload(engine, "task", DialogAction.BACK), state, sender)
    # Шаг выбора: прежний вариант отмечен.
    texts = [t for t, _ in _buttons(sender.last)]
    assert LAYOUT.selected_mark + "Физика" in texts
    assert "Оставить как есть" in texts


@pytest.mark.asyncio
async def test_keep_button_without_draft_is_stale(runner, engine, state, sender):
    await runner.start(state, sender)
    turn = await runner.on_callback(
        payload(engine, "subject", DialogAction.KEEP), state, sender
    )
    assert turn.alert == aiogram_integration.runner.STALE_BUTTON_ALERT


# ── Шаг подтверждения ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_step_edit_and_confirm(state, sender):
    engine = DialogEngine.from_list(
        [
            {"id": "title", "type": "text", "text": "Название"},
            {
                "id": "confirm",
                "type": "confirm",
                "text": "Переслать «{title}»?",
                "choices": {"title": "✏️ Название"},
            },
        ],
        dialog_id="forward",
    )
    runner = DialogRunner(engine, layout=LAYOUT)
    await runner.start(state, sender)
    await runner.on_text("Выпуск 1", state, sender)

    assert sender.last.text == "Переслать «Выпуск 1»?"
    buttons = dict(_buttons(sender.last))
    assert "✏️ Название" in buttons and "✅ Подтвердить" in buttons

    await runner.on_text("да", state, sender)
    assert sender.last.error == "Выберите вариант с помощью кнопок."

    await runner.on_callback(buttons["✏️ Название"], state, sender)
    assert sender.last.step.id == "title"
    await runner.on_text("Выпуск 2", state, sender)
    assert sender.last.text == "Переслать «Выпуск 2»?"

    turn = await runner.on_callback(buttons["✅ Подтвердить"], state, sender)
    assert turn.finished
    assert turn.answers == {"title": "Выпуск 2", "confirm": True}


# ── Истечение сессии ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expired_dialog_is_closed_with_message(state, sender):
    now = [0.0]
    engine = DialogEngine(
        DialogEngine.from_list(STEPS).steps,
        dialog_id="homework",
        ttl=30,
        clock=lambda: now[0],
    )
    runner = DialogRunner(engine, layout=LAYOUT)
    await runner.start(state, sender)
    anchor_views = len(sender.views)

    now[0] = 31
    turn = await runner.on_text("что-то", state, sender)
    assert turn.expired and turn.cancelled
    assert turn.alert == "Анкета устарела — начните заново."
    assert len(sender.views) == anchor_views + 1
    assert sender.last.text == turn.alert and sender.last.keyboard is None
    assert (await runner.storage.load(state))[0] is None

    second = await runner.on_text("ещё", state, sender)
    assert second.handled is False
