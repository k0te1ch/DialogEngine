import pytest

from dialog_engine.step import DialogStep

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

DialogAction = aiogram_integration.DialogAction
DialogCallback = aiogram_integration.DialogCallback
KeyboardLayout = aiogram_integration.KeyboardLayout
clamp_page = aiogram_integration.clamp_page
page_count = aiogram_integration.page_count
render_keyboard = aiogram_integration.render_keyboard
step_options = aiogram_integration.step_options

LAYOUT = KeyboardLayout(row_width=2, page_size=4)

SUBJECTS = {
    "math": "Математика",
    "phys": "Физика",
    "prog": "Программирование",
    "eng": "Английский",
    "hist": "История",
    "chem": "Химия",
    "bio": "Биология",
    "geo": "География",
    "phil": "Философия",
}


def choice_step(choices=None, **kwargs):
    kwargs.setdefault("required", True)
    return DialogStep(
        id="subject",
        type="choice",
        text="Выберите предмет",
        choices=SUBJECTS if choices is None else choices,
        **kwargs,
    )


def option_rows(markup):
    """Ряды с вариантами ответа — без пагинации и служебных кнопок."""
    rows = []
    for row in markup.inline_keyboard:
        actions = {DialogCallback.unpack(b.callback_data).action for b in row}
        if actions == {DialogAction.PICK}:
            rows.append(row)
    return rows


def option_labels(markup):
    return [button.text for row in option_rows(markup) for button in row]


def nav_row(markup):
    for row in markup.inline_keyboard:
        actions = {DialogCallback.unpack(b.callback_data).action for b in row}
        if actions & {DialogAction.PAGE, DialogAction.NOOP}:
            return row
    return None


# ── Раскладка ─────────────────────────────────────────────────────────────────


def test_options_are_split_by_row_width():
    markup = render_keyboard(choice_step(), layout=LAYOUT)

    assert [len(row) for row in option_rows(markup)] == [2, 2]


def test_last_row_keeps_the_remainder():
    layout = KeyboardLayout(row_width=2, page_size=3)
    markup = render_keyboard(choice_step(), layout=layout)

    assert [len(row) for row in option_rows(markup)] == [2, 1]


def test_pick_callback_carries_absolute_option_index():
    markup = render_keyboard(choice_step(), page=1, layout=LAYOUT)
    first = DialogCallback.unpack(option_rows(markup)[0][0].callback_data)

    assert first.action is DialogAction.PICK
    assert first.arg == 4  # пятый вариант, а не первый на странице


def test_boolean_step_gets_yes_no_buttons():
    step = DialogStep(id="confirm", type="boolean", text="Готово?")

    assert [option.key for option in step_options(step)] == ["true", "false"]
    assert option_labels(render_keyboard(step)) == ["Да", "Нет"]


def test_text_step_has_no_option_buttons():
    step = DialogStep(id="task", type="text", text="Текст задания")

    assert option_rows(render_keyboard(step)) == []


# ── Пагинация ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("total", "page_size", "expected"),
    [(0, 8, 1), (1, 8, 1), (8, 8, 1), (9, 8, 2), (16, 8, 2), (17, 8, 3)],
)
def test_page_count(total, page_size, expected):
    assert page_count(total, page_size) == expected


def test_page_count_rejects_non_positive_page_size():
    with pytest.raises(ValueError):
        page_count(10, 0)


@pytest.mark.parametrize(
    ("page", "expected"), [(-5, 0), (0, 0), (1, 1), (2, 2), (99, 2)]
)
def test_clamp_page(page, expected):
    assert clamp_page(page, total_pages=3) == expected


def test_single_page_has_no_navigation():
    markup = render_keyboard(choice_step({"math": "Математика"}), layout=LAYOUT)

    assert nav_row(markup) is None


def test_exactly_one_full_page_has_no_navigation():
    choices = dict(list(SUBJECTS.items())[: LAYOUT.page_size])
    markup = render_keyboard(choice_step(choices), layout=LAYOUT)

    assert nav_row(markup) is None
    assert len(option_labels(markup)) == LAYOUT.page_size


def test_middle_page_has_both_arrows_active():
    markup = render_keyboard(choice_step(), page=1, layout=LAYOUT)
    prev, indicator, nxt = nav_row(markup)

    assert DialogCallback.unpack(prev.callback_data).action is DialogAction.PAGE
    assert DialogCallback.unpack(prev.callback_data).arg == 0
    assert DialogCallback.unpack(nxt.callback_data).action is DialogAction.PAGE
    assert DialogCallback.unpack(nxt.callback_data).arg == 2
    assert indicator.text == "2/3"


def test_first_page_disables_the_left_arrow():
    markup = render_keyboard(choice_step(), page=0, layout=LAYOUT)
    prev, indicator, nxt = nav_row(markup)

    assert DialogCallback.unpack(prev.callback_data).action is DialogAction.NOOP
    assert DialogCallback.unpack(nxt.callback_data).action is DialogAction.PAGE
    assert indicator.text == "1/3"


def test_last_page_disables_the_right_arrow():
    markup = render_keyboard(choice_step(), page=2, layout=LAYOUT)
    prev, indicator, nxt = nav_row(markup)

    assert DialogCallback.unpack(prev.callback_data).action is DialogAction.PAGE
    assert DialogCallback.unpack(nxt.callback_data).action is DialogAction.NOOP
    assert indicator.text == "3/3"
    assert option_labels(markup) == ["Философия"]


def test_page_out_of_range_falls_back_to_the_last_page():
    markup = render_keyboard(choice_step(), page=99, layout=LAYOUT)

    assert option_labels(markup) == ["Философия"]


# ── Служебные кнопки ──────────────────────────────────────────────────────────


def test_back_button_appears_only_when_allowed():
    step = choice_step()

    without = render_keyboard(step, can_go_back=False, layout=LAYOUT)
    with_back = render_keyboard(step, can_go_back=True, layout=LAYOUT)

    assert not _actions(without) & {DialogAction.BACK}
    assert DialogAction.BACK in _actions(with_back)


def test_optional_step_offers_skip():
    step = choice_step(required=False)

    assert DialogAction.SKIP in _actions(render_keyboard(step, layout=LAYOUT))


def test_cancel_is_opt_in():
    layout = KeyboardLayout(page_size=4, show_cancel=True)

    assert DialogAction.CANCEL in _actions(
        render_keyboard(choice_step(), layout=layout)
    )
    assert DialogAction.CANCEL not in _actions(
        render_keyboard(choice_step(), layout=LAYOUT)
    )


def test_multi_choice_marks_selected_and_offers_done():
    step = DialogStep(
        id="days",
        type="multi_choice",
        text="Дни",
        choices={"mon": "Понедельник", "tue": "Вторник"},
    )

    markup = render_keyboard(step, selected=["tue"], layout=LAYOUT)

    assert option_labels(markup) == ["Понедельник", "✅ Вторник"]
    assert DialogAction.DONE in _actions(markup)


def test_every_callback_fits_telegram_limit():
    step = DialogStep(
        id="очень_длинный_идентификатор_шага_мастера_добавления_домашки",
        type="choice",
        text="Выберите предмет",
        required=False,
        choices={f"длинный_ключ_варианта_номер_{i}": f"Вариант {i}" for i in range(20)},
    )

    markup = render_keyboard(step, page=1, can_go_back=True, layout=LAYOUT)

    for row in markup.inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode("utf-8")) <= 64


def _actions(markup):
    return {
        DialogCallback.unpack(button.callback_data).action
        for row in markup.inline_keyboard
        for button in row
    }


def test_force_reply_is_off_by_default():
    assert render_keyboard(choice_step()).force_reply is None


def test_force_reply_is_set_for_every_step():
    layout = KeyboardLayout(force_reply=True)

    assert render_keyboard(choice_step(), layout=layout).force_reply is True
