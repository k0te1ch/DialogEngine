"""Пример использования асинхронных валидаторов и резолверов в DialogEngine."""

import asyncio

from dialog_engine import DialogEngine
from dialog_engine.validators import _ASYNC_VALIDATORS


async def async_email_validator(value: str, step):
    """Асинхронный валидатор email с проверкой через API."""
    import re

    from dialog_engine.exceptions import ValidationError

    # Простая синхронная проверка формата
    text = str(value).strip().lower()
    if not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text):
        raise ValidationError(
            f"Некорректный адрес электронной почты: {text!r}.", step.id
        )

    # Имитация асинхронной проверки через API
    print(f"Проверка email через API: {text}")
    await asyncio.sleep(0.1)  # Имитация сетевого запроса

    # Дополнительная проверка (например, проверка домена)
    if "example" in text:
        raise ValidationError(
            f"Домен example.com не поддерживается: {text!r}.", step.id
        )

    return text


async def async_text_resolver(text: str, context: dict):
    """Асинхронный резолвер текста с динамическим контентом."""
    print(f"Асинхронное разрешение текста: {text}")
    await asyncio.sleep(0.05)  # Имитация асинхронной операции

    # Поддержка форматирования с контекстом
    if "{" in text and "}" in text:
        return text.format(**context)
    return text


async def main():
    """Демонстрация работы с асинхронными валидаторами и резолверами."""

    # Регистрация асинхронного валидатора
    _ASYNC_VALIDATORS["email"] = async_email_validator

    # Создание диалога с асинхронным резолвером
    steps = [
        {"id": "name", "type": "text", "text": "Ваше имя?", "required": True},
        {"id": "email", "type": "email", "text": "Ваш email?", "required": True},
        {
            "id": "confirm",
            "type": "choice",
            "text": "Привет, {name}! Подтверждаете email {email}?",
            "choices": {"yes": "Да", "no": "Нет"},
            "next": {"yes": "done", "no": "email"},
        },
        {
            "id": "done",
            "type": "text",
            "text": "Спасибо за регистрацию, {name}!",
            "required": False,
            "next": "_end",
        },
    ]

    engine = DialogEngine.from_list(steps, text_resolver=async_text_resolver)

    # Создание сессии
    session = engine.create_session()

    print("=== Асинхронный диалог ===")

    # Шаг 1: Имя
    step = engine.current_step(session)
    print(f"Вопрос: {await engine.async_resolve_text(step, session)}")
    next_step = await engine.async_submit(session, "Иван")
    print("Ответ: Иван")

    # Шаг 2: Email
    step = next_step
    print(f"Вопрос: {await engine.async_resolve_text(step, session)}")
    try:
        next_step = await engine.async_submit(session, "ivan@example.com")
        print("Ответ: ivan@example.com")
    except Exception as e:
        print(f"Ошибка: {e}")
        next_step = await engine.async_submit(session, "ivan@gmail.com")
        print("Ответ: ivan@gmail.com")

    # Шаг 3: Подтверждение
    step = next_step
    print(f"Вопрос: {await engine.async_resolve_text(step, session)}")
    next_step = await engine.async_submit(session, "yes")
    print("Ответ: Да")

    # Шаг 4: Завершение
    if next_step:
        step = next_step
        print(f"Сообщение: {await engine.async_resolve_text(step, session)}")
        await engine.async_submit(session, "")

    print("\n=== Сессия завершена ===")
    print(f"Статус: {session.status}")
    print(f"Ответы: {session.answers}")


if __name__ == "__main__":
    asyncio.run(main())
