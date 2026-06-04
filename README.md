# DialogEngine

[![Python CI](https://github.com/k0te1ch/DialogEngine/actions/workflows/python-app.yml/badge.svg)](https://github.com/k0te1ch/DialogEngine/actions/workflows/python-app.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`DialogEngine` — лёгкий движок многошаговых диалогов на чистом Python (stdlib, без
обязательных зависимостей). Помогает строить сложные form-driven сценарии и
Telegram-ботов без спагетти из хендлеров: схема диалога описывается данными, а
движок управляет навигацией, валидацией и состоянием сессии.

## Возможности

- Описание диалога данными (`dict` / JSON / список шагов) — без хардкода переходов.
- Условные переходы между шагами (`next` по значению ответа).
- Встроенная валидация ответов + кастомные валидаторы, синхронные и асинхронные.
- Резолверы текста с подстановкой из накопленных ответов (`{name}` и т.п.).
- Управление сессией: статусы `IN_PROGRESS / COMPLETED / CANCELLED`.
- Опциональные extras: `pydantic`-валидация, загрузка схем из YAML, интеграция с `aiogram`.

## Установка

```bash
pip install dialog-engine
# с дополнительными возможностями:
pip install "dialog-engine[validation,yaml,aiogram]"
```

Для разработки используется [Poetry](https://python-poetry.org/):

```bash
poetry install --all-extras
```

## Быстрый старт

```python
from dialog_engine import DialogEngine

engine = DialogEngine.from_list([
    {"id": "name", "type": "text", "text": "Как вас зовут?"},
    {"id": "age", "type": "number", "text": "Сколько вам лет?", "min": 1},
])

session = engine.create_session()

while (step := engine.current_step(session)) is not None:
    answer = input(engine.resolve_text(step, session) + " ")
    try:
        engine.submit(session, answer)
    except ValueError as exc:
        print("Ошибка:", exc)

print("Готово!", session.answers)
```

## Асинхронный режим

Движок поддерживает асинхронные валидаторы и резолверы текста через
`async_submit` / `async_resolve_text`. Полный пример —
[examples/async_validators_example.py](examples/async_validators_example.py).

## Основной API

- `DialogEngine` — загрузка схемы и управление потоком диалога.
- `DialogSession` / `SessionStatus` — состояние одного запуска диалога.
- `DialogStep` / `StepType` — описание шага и его тип.
- `validate` — встроенная валидация ответов.
- `DialogError`, `ValidationError`, `StepNotFoundError` — иерархия исключений.

## Разработка

```bash
poetry install --all-extras
poetry run pre-commit install --hook-type pre-commit --hook-type commit-msg
poetry run pytest
poetry run pre-commit run --all-files
```

Коммиты — по [Conventional Commits](https://www.conventionalcommits.org/);
формат проверяет хук `commitizen`. Релизы, теги и `CHANGELOG.md` полностью
автоматизированы через [release-please](https://github.com/googleapis/release-please).
Полный гайд с диаграммами — [docs/WORKFLOW.md](docs/WORKFLOW.md).

## Структура проекта

- `dialog_engine/` — исходный код библиотеки.
- `tests/` — набор тестов (`pytest`).
- `examples/` — примеры использования.
- `docs/WORKFLOW.md` — гайд по веткам, коммитам и релизам.
- `.github/workflows/` — CI и release-please.

## Лицензия

[MIT](LICENSE)
