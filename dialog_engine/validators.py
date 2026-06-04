"""Built-in answer validators for each step type.

Each validator:
  - accepts (value, step) where *value* is the raw user input
  - returns a cleaned / normalised value on success
  - raises ValidationError on failure
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

from .exceptions import ValidationError
from .step import DialogStep

# ── Per-type validators ───────────────────────────────────────────────────────


def _validate_text(value: Any, step: DialogStep) -> str:
    text = str(value).strip()
    if not text:
        if step.required:
            raise ValidationError("Это поле обязательно для заполнения.", step.id)
        return text
    if step.min is not None and len(text) < int(step.min):
        raise ValidationError(
            f"Слишком короткий текст (минимум {int(step.min)} символов).", step.id
        )
    if step.max is not None and len(text) > int(step.max):
        raise ValidationError(
            f"Слишком длинный текст (максимум {int(step.max)} символов).", step.id
        )
    if step.pattern is not None and not re.fullmatch(step.pattern, text):
        raise ValidationError("Текст не соответствует ожидаемому формату.", step.id)
    return text


def _validate_number(value: Any, step: DialogStep) -> int | float:
    try:
        num = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise ValidationError(
            f"Ожидается число, получено: {value!r}.", step.id
        ) from None
    if step.min is not None and num < step.min:
        raise ValidationError(f"Число должно быть не меньше {step.min}.", step.id)
    if step.max is not None and num > step.max:
        raise ValidationError(f"Число должно быть не больше {step.max}.", step.id)
    return int(num) if num == int(num) else num


def _validate_email(value: Any, step: DialogStep) -> str:
    text = str(value).strip().lower()
    if not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text):
        raise ValidationError(
            f"Некорректный адрес электронной почты: {text!r}.", step.id
        )
    return text


def _validate_boolean(value: Any, step: DialogStep) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        if value.lower() in ("1", "true", "yes", "да", "y"):
            return True
        if value.lower() in ("0", "false", "no", "нет", "n"):
            return False
    raise ValidationError(
        f"Ожидается булево значение (true/false/да/нет), получено: {value!r}.", step.id
    )


def _validate_choice(value: Any, step: DialogStep) -> str:
    key = str(value)
    if key not in step.choices:
        valid = ", ".join(step.choices.keys())
        raise ValidationError(
            f"Неверный вариант: {key!r}. Допустимые: {valid}.", step.id
        )
    return key


def _validate_multi_choice(value: Any, step: DialogStep) -> list[str]:
    if isinstance(value, str):
        items = [v.strip() for v in value.split(",") if v.strip()]
    elif isinstance(value, (list, tuple, set)):
        items = [str(v) for v in value]
    else:
        raise ValidationError(
            f"Ожидается список вариантов, получено: {value!r}.", step.id
        )

    invalid = [v for v in items if v not in step.choices]
    if invalid:
        valid = ", ".join(step.choices.keys())
        raise ValidationError(
            f"Недопустимые варианты: {invalid}. Допустимые: {valid}.", step.id
        )
    if step.min is not None and len(items) < int(step.min):
        raise ValidationError(f"Выберите не менее {int(step.min)} вариантов.", step.id)
    if step.max is not None and len(items) > int(step.max):
        raise ValidationError(f"Выберите не более {int(step.max)} вариантов.", step.id)
    return items


def _validate_media(value: Any, step: DialogStep, label: str) -> list[Any]:
    items: list[Any] = value if isinstance(value, list) else [value]
    min_count = int(step.min) if step.min is not None else 1
    max_count = int(step.max) if step.max is not None else 1
    if len(items) < min_count:
        raise ValidationError(
            f"Необходимо загрузить минимум {min_count} {label}.", step.id
        )
    if len(items) > max_count:
        raise ValidationError(f"Можно загрузить не более {max_count} {label}.", step.id)
    return items


def _validate_photo(value: Any, step: DialogStep) -> list[Any]:
    return _validate_media(value, step, "фото")


def _validate_file(value: Any, step: DialogStep) -> list[Any]:
    return _validate_media(value, step, "файлов")


# ── Registry ──────────────────────────────────────────────────────────────────

AsyncValidator = Callable[[Any, DialogStep], Awaitable[Any]]

_VALIDATORS: dict[str, Any] = {
    "text": _validate_text,
    "number": _validate_number,
    "email": _validate_email,
    "boolean": _validate_boolean,
    "choice": _validate_choice,
    "multi_choice": _validate_multi_choice,
    "photo": _validate_photo,
    "file": _validate_file,
}

_ASYNC_VALIDATORS: dict[str, AsyncValidator] = {}


def sync_validate(step: DialogStep, value: Any) -> Any:
    """Validate *value* against *step*'s rules synchronously.

    Returns the cleaned value on success.
    Raises :class:`ValidationError` on failure.
    Unknown step types pass through without validation.
    """
    is_empty = value is None or (isinstance(value, str) and not value.strip())
    if is_empty:
        if step.required:
            raise ValidationError("Это поле обязательно для заполнения.", step.id)
        return value  # optional → accept empty

    fn = _VALIDATORS.get(step.type)
    if fn is None:
        return value
    return fn(value, step)


def validate(step: DialogStep, value: Any) -> Any:
    """Validate *value* against *step*'s rules.

    Returns the cleaned value on success.
    Raises :class:`ValidationError` on failure.
    Unknown step types pass through without validation.
    """
    return sync_validate(step, value)


async def async_validate(step: DialogStep, value: Any) -> Any:
    """Validate *value* against *step*'s rules asynchronously.

    Returns the cleaned value on success.
    Raises :class:`ValidationError` on failure.
    Unknown step types pass through without validation.
    """
    is_empty = value is None or (isinstance(value, str) and not value.strip())
    if is_empty:
        if step.required:
            raise ValidationError("Это поле обязательно для заполнения.", step.id)
        return value  # optional → accept empty

    fn = _ASYNC_VALIDATORS.get(step.type) or _VALIDATORS.get(step.type)
    if fn is None:
        return value

    if asyncio.iscoroutinefunction(fn):
        return await fn(value, step)
    else:
        return fn(value, step)
