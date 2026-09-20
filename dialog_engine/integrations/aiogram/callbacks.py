"""Кодирование и разбор ``callback_data`` для клавиатур диалога.

Telegram ограничивает ``callback_data`` 64 байтами, а идентификаторы шагов и
ключи ``DialogStep.choices`` в схеме произвольно длинные — «выбор_предмета» и
«Дискретная математика и математическая логика» одинаково законны. Поэтому в
payload едут не сами значения, а короткие суррогаты:

* шаг — восьмисимвольный токен (усечённый ``blake2s`` от ``step.id``);
* вариант ответа — порядковый номер в ``step.choices``.

Токен шага нужен не для навигации (текущий шаг и так известен из сессии), а
чтобы отличить нажатие на актуальной клавиатуре от нажатия на устаревшей —
например, в сообщении, которое пользователь пролистал вверх.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from dialog_engine.exceptions import DialogError
from dialog_engine.step import DialogStep

PREFIX = "de"
SEPARATOR = ":"
TOKEN_LENGTH = 8
MAX_PAYLOAD_BYTES = 64


class CallbackParseError(DialogError):
    """Payload не принадлежит dialog_engine или повреждён."""


class DialogAction(StrEnum):
    """Что означает нажатие кнопки.

    Значения намеренно однобуквенные: каждый лишний байт отнимается от бюджета
    в 64 байта.
    """

    PICK = "p"
    """Выбран вариант с индексом ``arg``."""

    PAGE = "g"
    """Переход на страницу ``arg`` при пагинации вариантов."""

    DONE = "d"
    """Подтверждение набора вариантов на шаге ``multi_choice``."""

    BACK = "b"
    SKIP = "s"
    CANCEL = "c"

    NOOP = "n"
    """Кнопка-заглушка (индикатор страницы, неактивная стрелка)."""


def step_token(step_id: str) -> str:
    """Короткий стабильный токен шага.

    Стабильный между перезапусками процесса, поэтому клавиатура, отправленная
    до рестарта бота, продолжает работать.
    """
    digest = hashlib.blake2s(step_id.encode("utf-8"), digest_size=8).hexdigest()
    return digest[:TOKEN_LENGTH]


def find_step_by_token(steps: list[DialogStep], token: str) -> DialogStep | None:
    """Найти шаг по токену; ``None``, если такого шага в схеме нет."""
    for step in steps:
        if step_token(step.id) == token:
            return step
    return None


@dataclass(frozen=True, slots=True)
class DialogCallback:
    """Разобранное содержимое ``callback_data``."""

    action: DialogAction
    step_token: str
    arg: int = 0

    def pack(self) -> str:
        """Собрать payload для кнопки.

        Raises:
            DialogError: если payload не помещается в лимит Telegram. При
                фиксированной длине токена это недостижимо, но проверка
                защищает от будущих правок формата.
        """
        payload = SEPARATOR.join(
            (PREFIX, self.action.value, self.step_token, str(self.arg))
        )
        if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise DialogError(
                f"callback_data длиной {len(payload.encode('utf-8'))} байт "
                f"превышает лимит Telegram в {MAX_PAYLOAD_BYTES} байт: {payload!r}"
            )
        return payload

    @classmethod
    def unpack(cls, payload: str | None) -> DialogCallback:
        """Разобрать payload кнопки.

        Raises:
            CallbackParseError: payload пустой, чужой или неверной формы.
        """
        if not payload:
            raise CallbackParseError("Пустой callback_data.")
        parts = payload.split(SEPARATOR)
        if len(parts) != 4 or parts[0] != PREFIX:
            raise CallbackParseError(f"Чужой callback_data: {payload!r}")
        _, raw_action, token, raw_arg = parts
        try:
            action = DialogAction(raw_action)
        except ValueError:
            raise CallbackParseError(
                f"Неизвестное действие {raw_action!r} в {payload!r}"
            ) from None
        try:
            arg = int(raw_arg)
        except ValueError:
            raise CallbackParseError(
                f"Аргумент {raw_arg!r} не число в {payload!r}"
            ) from None
        return cls(action=action, step_token=token, arg=arg)


def build(action: DialogAction, step: DialogStep, arg: int = 0) -> str:
    """Короткая форма записи ``DialogCallback(...).pack()`` для шага."""
    return DialogCallback(action, step_token(step.id), arg).pack()
