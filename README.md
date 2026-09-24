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

## aiogram 3 integration

Optional layer that turns a dialog schema into a Telegram wizard. Install with
the `aiogram` extra; the core package never imports aiogram.

```python
from aiogram import Dispatcher
from dialog_engine import DialogEngine
from dialog_engine.integrations.aiogram import (
    DefaultSender, DialogRunner, KeyboardLayout, build_dialog_router,
)

engine = DialogEngine.from_file("dialogs/homework.json")
runner = DialogRunner(engine, layout=KeyboardLayout(row_width=2, page_size=6))

dispatcher = Dispatcher()
dispatcher.include_router(
    build_dialog_router(runner, sender_factory=DefaultSender, on_complete=save)
)
```

What it gives you:

- `render_keyboard` — `step.choices` as an inline keyboard, with paging
  (`‹ 2/3 ›`) once the options no longer fit one screen. Paging state is UI
  state and never lands in `session.answers`.
- Short `callback_data` — a step token plus an option index, so long step IDs
  and long choice keys still fit Telegram's 64-byte limit.
- `DialogRunner` — button and text input, validation errors shown in place
  without resetting the step, `back` / `skip` / `cancel`.
- `FSMDialogStorage` — the session lives in aiogram's `FSMContext`, so a
  wizard survives a process restart.
- `DialogSender` — a protocol, not a hardcoded `bot.send_message`. The default
  implementation sends and edits plain messages; replace it to answer with
  `sendRichMessage` or anything else. Editing goes through the same protocol.
- `EphemeralSender` — shows the wizard in a group as an ephemeral message
  (Bot API 10.3) that only the member filling it in can see; with an ephemeral
  entry command and `force_reply`, the answers stay invisible too.

### Ephemeral messages in groups

An ephemeral message needs a receiver and, unless the bot is a chat admin, a
trigger no older than 15 seconds: a button press (`callback_query_id`) or an
ephemeral command. Both come from the update, so pass `event_sender_factory`
instead of `sender_factory`:

```python
from dialog_engine.integrations.aiogram import EphemeralSender, ephemeral_in_groups

router = build_dialog_router(runner, event_sender_factory=EphemeralSender.for_event)
# or: ephemeral in groups, plain messages in private chats
router = build_dialog_router(runner, event_sender_factory=ephemeral_in_groups)

@start_router.message(Command("homework"))
async def start(message: Message, state: FSMContext) -> None:
    await runner.start(state, EphemeralSender.for_event(message))
```

Steps are edited in place with `editEphemeralMessageText`; the 15-second window
limits sending, not editing, so a wizard keeps working for as long as the user
takes. If the message is gone (the client restarted or it expired), the edit
fails with `MESSAGE_NOT_FOUND` and a new message is sent — which again needs a
fresh trigger or admin rights. Requires `aiogram>=3.31`.

#### A wizard the group never sees

A user's reply to an ephemeral message is itself ephemeral, so the whole
conversation can stay invisible to everyone else:

- Declare the entry command with `is_ephemeral=True` in `setMyCommands`. The
  user's command is then delivered to the bot alone, and answering it needs no
  admin rights — `EphemeralSender.for_event(message)` replies to it.
- Set `KeyboardLayout(force_reply=True)`. The client opens the reply field, so
  the answer arrives as a reply and stays ephemeral. Telegram forbids changing
  `force_reply` when a keyboard is edited, so it applies to every step of the
  dialog, including button-only ones.
- Leave `text_answers` alone: ephemeral answers are never deleted (there is
  nothing to hide and `deleteMessage` does not accept them). The policy only
  covers ordinary messages, which the group can read.

Verified live on Bot API 10.3: command, questions and answers all carry the
"visible only to you" mark, and nothing lands in the group timeline.

Full example: [examples/aiogram_homework_wizard.py](examples/aiogram_homework_wizard.py).

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
- `dialog_engine/integrations/aiogram/` — the optional aiogram 3 layer.
- `tests/` — the test suite (`pytest`).
- `examples/` — usage examples.
- `docs/WORKFLOW.md` — guide to branches, commits, and releases.
- `.github/workflows/` — CI and release-please.

## License

[MIT](LICENSE)
