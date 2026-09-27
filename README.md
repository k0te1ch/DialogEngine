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

## Step validators and session context

A step can carry its own validator. It runs after the built-in check for the
step type, may be sync or async, and receives a `StepContext` with the step,
the answers so far and the session context. Return the value to store
(`None` keeps it as is) or raise `ValidationError` to keep the user on the step.

The session context holds caller data for one run — language, IDs, values
computed by validators. It is saved with the session, so keep it
JSON-serialisable. A text resolver that takes three arguments receives it too;
two-argument resolvers keep working.

```python
from dialog_engine import DialogEngine, StepContext, ValidationError

async def parse_template(text: str, ctx: StepContext) -> dict:
    info = parse(text, kind=ctx.answers["kind"])
    if info is None:
        raise ValidationError("Template does not match", ctx.step.id)
    ctx.context["number"] = info["number"]
    return info

engine = DialogEngine.from_list(
    steps,
    validators={"template": parse_template},
    text_resolver=lambda key, answers, context: i18n[context["lang"]][key],
)
session = engine.create_session(context={"lang": "en"})
```

With aiogram, pass the context to `runner.start(state, sender, context=...)`;
the final `DialogTurn.context` returns it. The old process-wide
`_ASYNC_VALIDATORS` registry still works but is deprecated.

## Going back without losing the answer

`back()` and `jump_to()` take the step's answer out of `session.answers` and
keep it in `session.drafts`. `engine.draft(session)` returns it and
`engine.keep(session)` (or `async_keep`) submits it again, through validation
and branching, so a kept answer follows its old route and a changed one takes
the new route. Drafts are saved with the session and cleared when it
completes.

The aiogram runner marks the previous choice on the keyboard and adds a
"keep" button (`de.button.keep`, or `de.button.keep_value` with the old text
for text, number and email steps).

## Confirmation step

A `confirm` step shows a summary and waits for confirmation. Its text is
formatted with the answers (`{step_id}`; lists are joined, unknown
placeholders stay as they are). `choices` map step IDs to "edit" buttons.

```json
{"id": "confirm", "type": "confirm",
 "text": "Forward \"{title}\" to the channel?",
 "choices": {"title": "Edit title"}}
```

Editing uses `jump_to(session, step_id, return_to="confirm")`: after the edited
step is answered, the dialog follows its route through steps that already
have answers and stops at the summary, or earlier at a step the edit left
unanswered (a new branch). The answer of a confirm step is `True`; with an
empty `choices` it is a plain "are you sure?" step. In aiogram, the runner
draws the edit buttons and a confirm button (`de.button.confirm`). Telegram
limits a message to 4096 characters, so keep summaries short.

## Translating errors and labels

Every built-in validation error has a message key (`ValidationError.key`) and
placeholder values (`ValidationError.params`); the aiogram layer also asks the
resolver for its service buttons, alerts and the labels of `choices`. The
resolver receives the key like any step text: return a translation, or the key
unchanged to keep the built-in Russian text. Placeholders are filled after
translation.

```python
EN = {"de.error.text.min": "At least {min} characters", "de.button.back": "Back"}

def resolver(key, answers, context):
    return EN.get(key, key) if context.get("lang") == "en" else key

engine.resolve_error(exc, session)  # → "At least 3 characters"
```

A custom validator can raise `ValidationError("my.key")` or pass
`key=` / `params=` explicitly. The full list of keys with default texts is
`dialog_engine.DEFAULT_MESSAGES`:

| Key | Placeholders |
|---|---|
| `de.error.required` | — |
| `de.error.text.min` / `.max` / `.pattern` | `min` / `max` / — |
| `de.error.number.invalid` / `.min` / `.max` | `value` / `min` / `max` |
| `de.error.email.invalid`, `de.error.boolean.invalid` | `value` |
| `de.error.choice.invalid` | `value`, `valid` |
| `de.error.multi_choice.type` / `.invalid` / `.min` / `.max` | `value` / `value`, `valid` / `min` / `max` |
| `de.error.photo.min` / `.max`, `de.error.file.min` / `.max` | `min` / `max` |
| `de.error.media.mime` / `.extension` / `.size` | `allowed` / `allowed` / `max_mb`, `max_size` |
| `de.error.file.expected`, `de.error.photo.expected`, `de.error.media.unexpected` | — |
| `de.button.back` / `.skip` / `.cancel` / `.done` / `.yes` / `.no` / `.keep` / `.confirm` | — |
| `de.button.keep_value` | `value` |
| `de.error.button_required`, `de.alert.no_session`, `de.alert.stale_button` | — |

A resolver that does not know a `de.button.*` key keeps the text from
`KeyboardLayout`, so layouts customised by hand still work.

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

### File and photo steps

`file` / `photo` steps can check more than the count: `mime_types`
(`"audio/*"` matches the family), `extensions` (case-insensitive) and
`max_size` in bytes.

```json
{"id": "mp3", "type": "file", "text": "Send the MP3",
 "mime_types": ["audio/mpeg"], "extensions": [".mp3"], "max_size": 209715200}
```

The router passes photos, documents, audio, video, voice and animations to
`runner.on_files()` as `FileInfo` (file_id, mime_type, file_name, file_size);
`message_files(message)` does the same extraction for your own handlers. With
constraints the stored answer is a list of `FileInfo` dicts; without them it
stays a list of `file_id` strings, as before. Missing metadata counts as a
mismatch. Each message is one answer: albums are not grouped.

### Several dialogs in one chat

Each runner stores its session under `dialog_engine:<dialog_id>`, and its
buttons carry a short dialog token, so routers of different dialogs can be
included side by side: a button reaches only its own runner. Sessions saved by
0.2 under the shared `dialog_engine` key are picked up and moved on first load.

Two copies of the same dialog (say, a confirmation per message) need their own
storage scope; build a runner for that scope in your handler:

```python
storage = FSMDialogStorage.for_engine(confirm_engine, scope=message.message_id)
runner = DialogRunner(confirm_engine, storage=storage)
```

`DialogEngine.restore_session()` returns `None` for a session of another
dialog, of another schema `version` (pass `version=` to the engine or put
`"version"` in the JSON), or pointing past the end of the schema. Text answers
go to the first included router whose dialog is active.

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
- `StepContext` / `StepValidator` — the per-step validator contract.
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
