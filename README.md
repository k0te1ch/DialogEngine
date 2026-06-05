# DialogEngine

[![Python CI](https://github.com/k0te1ch/DialogEngine/actions/workflows/python-app.yml/badge.svg)](https://github.com/k0te1ch/DialogEngine/actions/workflows/python-app.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`DialogEngine` is a lightweight multi-step dialog engine written in pure Python
(stdlib only, no required dependencies). It helps you build complex form-driven
flows and Telegram bots without handler spaghetti: the dialog is described as
data, and the engine drives navigation, validation, and session state.

## Features

- Describe the dialog as data (`dict` / JSON / a list of steps) — no hard-coded transitions.
- Conditional transitions between steps (`next` based on the answer value).
- Built-in answer validation plus custom validators, both sync and async.
- Text resolvers with substitution from collected answers (`{name}`, etc.).
- Session management with `IN_PROGRESS / COMPLETED / CANCELLED` statuses.
- Optional extras: `pydantic` validation, loading schemas from YAML, `aiogram` integration.

## Installation

The package is not published to PyPI; install it from source:

```bash
pip install git+https://github.com/k0te1ch/DialogEngine.git
# with optional features:
pip install "dialog-engine[validation,yaml,aiogram] @ git+https://github.com/k0te1ch/DialogEngine.git"
```

For development, the project uses [Poetry](https://python-poetry.org/):

```bash
poetry install --all-extras
```

## Quick start

```python
from dialog_engine import DialogEngine

engine = DialogEngine.from_list([
    {"id": "name", "type": "text", "text": "What is your name?"},
    {"id": "age", "type": "number", "text": "How old are you?", "min": 1},
])

session = engine.create_session()

while (step := engine.current_step(session)) is not None:
    answer = input(engine.resolve_text(step, session) + " ")
    try:
        engine.submit(session, answer)
    except ValueError as exc:
        print("Error:", exc)

print("Done!", session.answers)
```

## Async mode

The engine supports async validators and text resolvers via `async_submit` /
`async_resolve_text`. See the full example in
[examples/async_validators_example.py](examples/async_validators_example.py).

## Core API

- `DialogEngine` — loads a schema and drives the dialog flow.
- `DialogSession` / `SessionStatus` — state of a single dialog run.
- `DialogStep` / `StepType` — a step description and its type.
- `validate` — built-in answer validation.
- `DialogError`, `ValidationError`, `StepNotFoundError` — exception hierarchy.

## Development

```bash
poetry install --all-extras
poetry run pre-commit install --hook-type pre-commit --hook-type commit-msg
poetry run pytest
poetry run pre-commit run --all-files
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org/);
the format is enforced by the `commitizen` hook. Releases, tags, and
`CHANGELOG.md` are fully automated via
[release-please](https://github.com/googleapis/release-please). See the full
guide with diagrams: [English](docs/WORKFLOW.en.md) · [Русский](docs/WORKFLOW.md).

## Project layout

- `dialog_engine/` — the library source code.
- `tests/` — the test suite (`pytest`).
- `examples/` — usage examples.
- `docs/WORKFLOW.md` — guide to branches, commits, and releases.
- `.github/workflows/` — CI and release-please.

## License

[MIT](LICENSE)
