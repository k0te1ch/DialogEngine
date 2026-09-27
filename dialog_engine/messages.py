"""Message keys the engine emits and their built-in (Russian) texts.

Validation errors and service labels carry a key from this table.  A text
resolver that knows the key translates it; for any other key it should return
the key unchanged, and the built-in text is used instead.  Placeholders like
``{min}`` are filled from the error's ``params`` after translation.
"""

from __future__ import annotations

DEFAULT_MESSAGES: dict[str, str] = {
    # Validation errors
    "de.error.required": "Это поле обязательно для заполнения.",
    "de.error.text.min": "Слишком короткий текст (минимум {min} символов).",
    "de.error.text.max": "Слишком длинный текст (максимум {max} символов).",
    "de.error.text.pattern": "Текст не соответствует ожидаемому формату.",
    "de.error.number.invalid": "Ожидается число, получено: {value}.",
    "de.error.number.min": "Число должно быть не меньше {min}.",
    "de.error.number.max": "Число должно быть не больше {max}.",
    "de.error.email.invalid": "Некорректный адрес электронной почты: {value}.",
    "de.error.boolean.invalid": (
        "Ожидается булево значение (true/false/да/нет), получено: {value}."
    ),
    "de.error.choice.invalid": "Неверный вариант: {value}. Допустимые: {valid}.",
    "de.error.multi_choice.type": "Ожидается список вариантов, получено: {value}.",
    "de.error.multi_choice.invalid": (
        "Недопустимые варианты: {value}. Допустимые: {valid}."
    ),
    "de.error.multi_choice.min": "Выберите не менее {min} вариантов.",
    "de.error.multi_choice.max": "Выберите не более {max} вариантов.",
    "de.error.photo.min": "Необходимо загрузить минимум {min} фото.",
    "de.error.photo.max": "Можно загрузить не более {max} фото.",
    "de.error.file.min": "Необходимо загрузить минимум {min} файлов.",
    "de.error.file.max": "Можно загрузить не более {max} файлов.",
    "de.error.media.mime": "Неподходящий тип файла. Допустимые: {allowed}.",
    "de.error.media.extension": (
        "Неподходящее расширение файла. Допустимые: {allowed}."
    ),
    "de.error.media.size": "Файл слишком большой (максимум {max_mb} МБ).",
    "de.error.file.expected": "Отправьте файл.",
    "de.error.photo.expected": "Отправьте фото.",
    "de.error.media.unexpected": "Здесь нужен ответ текстом или кнопкой.",
    # Service buttons and alerts of the aiogram layer
    "de.button.back": "⬅️ Назад",
    "de.button.skip": "Пропустить",
    "de.button.cancel": "Отмена",
    "de.button.done": "Готово",
    "de.button.keep": "Оставить как есть",
    "de.button.confirm": "✅ Подтвердить",
    "de.button.keep_value": "Оставить: {value}",
    "de.button.yes": "Да",
    "de.button.no": "Нет",
    "de.error.button_required": "Выберите вариант с помощью кнопок.",
    "de.alert.no_session": "Диалог не запущен или уже завершён.",
    "de.alert.stale_button": "Кнопка устарела — ответьте на текущий вопрос.",
}


def default_text(key: str, params: dict[str, object] | None = None) -> str:
    """Built-in text for *key* with *params* filled in."""
    return DEFAULT_MESSAGES[key].format(**(params or {}))
