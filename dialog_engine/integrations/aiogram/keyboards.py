"""Сборка inline-клавиатуры по описанию шага.

Модуль намеренно чистый: он ничего не отправляет и не знает про сессию, а
принимает шаг и параметры отображения и возвращает
:class:`~aiogram.types.InlineKeyboardMarkup`. Благодаря этому раскладка и
пагинация тестируются без бота и без сети.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from dialog_engine.step import DialogStep

from .callbacks import DialogAction, build

BOOLEAN_KEYS = ("true", "false")
"""Ключи, которые уходят валидатору для шага типа ``boolean``."""


@dataclass(frozen=True, slots=True)
class KeyboardLayout:
    """Параметры отрисовки клавиатуры.

    Отделены от схемы диалога: одна и та же анкета в разных ботах может
    выглядеть по-разному, а ``DialogStep`` описывает смысл шага, а не вёрстку.
    """

    row_width: int = 2
    """Сколько кнопок вариантов в одном ряду."""

    page_size: int = 8
    """Сколько вариантов показывать на одной странице."""

    prev_text: str = "‹"
    next_text: str = "›"
    page_template: str = "{page}/{total}"
    back_text: str = "⬅️ Назад"
    skip_text: str = "Пропустить"
    cancel_text: str = "Отмена"
    done_text: str = "Готово"
    selected_mark: str = "✅ "
    """Префикс выбранного варианта на шаге ``multi_choice``."""

    boolean_labels: tuple[str, str] = ("Да", "Нет")
    show_back: bool = True
    show_cancel: bool = False


DEFAULT_LAYOUT = KeyboardLayout()


@dataclass(frozen=True, slots=True)
class Option:
    """Вариант ответа вместе с его позицией в исходном ``choices``.

    Индекс абсолютный (а не в пределах страницы), поэтому разбор нажатия не
    зависит от того, на какой странице пользователь был в момент клика.
    """

    index: int
    key: str
    label: str


def step_options(
    step: DialogStep, layout: KeyboardLayout = DEFAULT_LAYOUT
) -> list[Option]:
    """Варианты ответа для шага в порядке объявления.

    Для ``boolean`` вариантов в схеме нет, поэтому пара «да/нет» собирается из
    настроек раскладки.
    """
    if step.choices:
        return [
            Option(i, key, label) for i, (key, label) in enumerate(step.choices.items())
        ]
    if step.type == "boolean":
        return [
            Option(i, key, label)
            for i, (key, label) in enumerate(
                zip(BOOLEAN_KEYS, layout.boolean_labels, strict=True)
            )
        ]
    return []


def page_count(total: int, page_size: int) -> int:
    """Число страниц; для пустого списка вариантов — одна страница."""
    if page_size <= 0:
        raise ValueError("page_size должен быть положительным.")
    if total <= 0:
        return 1
    return -(-total // page_size)


def clamp_page(page: int, total_pages: int) -> int:
    """Привести номер страницы к допустимому диапазону.

    Страница приходит из ``callback_data``, то есть из внешнего мира, и может
    указывать на страницу, которой уже нет (схема диалога успела измениться).
    """
    return max(0, min(page, total_pages - 1))


def options_for_page(
    options: Sequence[Option], page: int, page_size: int
) -> list[Option]:
    """Срез вариантов, попадающих на страницу *page* (нумерация с нуля)."""
    start = page * page_size
    return list(options[start : start + page_size])


def render_keyboard(
    step: DialogStep,
    *,
    page: int = 0,
    selected: Iterable[str] = (),
    can_go_back: bool = False,
    layout: KeyboardLayout = DEFAULT_LAYOUT,
) -> InlineKeyboardMarkup:
    """Собрать клавиатуру шага.

    Args:
        step: шаг, для которого строится клавиатура.
        page: текущая страница вариантов (нумерация с нуля, значение
            приводится к допустимому диапазону).
        selected: ключи уже отмеченных вариантов — только для ``multi_choice``.
        can_go_back: показывать ли «Назад». Решение принимает вызывающий:
            клавиатура не видит историю сессии.
        layout: параметры отрисовки.
    """
    options = step_options(step, layout)
    total_pages = page_count(len(options), layout.page_size)
    current = clamp_page(page, total_pages)
    chosen = set(selected)

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for option in options_for_page(options, current, layout.page_size):
        prefix = layout.selected_mark if option.key in chosen else ""
        row.append(
            InlineKeyboardButton(
                text=f"{prefix}{option.label}",
                callback_data=build(DialogAction.PICK, step, option.index),
            )
        )
        if len(row) == layout.row_width:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if total_pages > 1:
        rows.append(_pagination_row(step, current, total_pages, layout))

    if step.type == "multi_choice":
        rows.append(
            [
                InlineKeyboardButton(
                    text=layout.done_text,
                    callback_data=build(DialogAction.DONE, step),
                )
            ]
        )

    service = _service_row(step, can_go_back=can_go_back, layout=layout)
    if service:
        rows.append(service)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pagination_row(
    step: DialogStep,
    page: int,
    total_pages: int,
    layout: KeyboardLayout,
) -> list[InlineKeyboardButton]:
    """Ряд «‹ 2/3 ›».

    На крайних страницах недоступная стрелка не убирается, а становится
    заглушкой: иначе кнопки съезжают под курсором и пользователь промахивается.
    """
    prev_action = DialogAction.PAGE if page > 0 else DialogAction.NOOP
    next_action = DialogAction.PAGE if page < total_pages - 1 else DialogAction.NOOP
    return [
        InlineKeyboardButton(
            text=layout.prev_text,
            callback_data=build(prev_action, step, max(page - 1, 0)),
        ),
        InlineKeyboardButton(
            text=layout.page_template.format(page=page + 1, total=total_pages),
            callback_data=build(DialogAction.NOOP, step, page),
        ),
        InlineKeyboardButton(
            text=layout.next_text,
            callback_data=build(next_action, step, min(page + 1, total_pages - 1)),
        ),
    ]


def _service_row(
    step: DialogStep,
    *,
    can_go_back: bool,
    layout: KeyboardLayout,
) -> list[InlineKeyboardButton]:
    """Ряд служебных кнопок: «Назад», «Пропустить», «Отмена»."""
    row: list[InlineKeyboardButton] = []
    if layout.show_back and can_go_back:
        row.append(
            InlineKeyboardButton(
                text=layout.back_text,
                callback_data=build(DialogAction.BACK, step),
            )
        )
    if not step.required:
        row.append(
            InlineKeyboardButton(
                text=layout.skip_text,
                callback_data=build(DialogAction.SKIP, step),
            )
        )
    if layout.show_cancel:
        row.append(
            InlineKeyboardButton(
                text=layout.cancel_text,
                callback_data=build(DialogAction.CANCEL, step),
            )
        )
    return row
