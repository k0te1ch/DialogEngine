import json
import tempfile
from pathlib import Path

import pytest

from dialog_engine import DialogEngine
from dialog_engine.exceptions import DialogError, StepNotFoundError, ValidationError
from dialog_engine.session import SessionStatus


def setup_function():
    global engine
    steps = [
        {"id": "name", "type": "text", "text": "Ваше имя?"},
        {"id": "age", "type": "number", "text": "Ваш возраст?", "min": 1},
        {
            "id": "confirm",
            "type": "choice",
            "text": "Продолжить?",
            "choices": {"yes": "Да", "no": "Нет"},
            "next": {"yes": "done", "no": "cancel"},
        },
        {
            "id": "done",
            "type": "text",
            "text": "Спасибо!",
            "required": False,
            "next": "_end",
        },
        {"id": "cancel", "type": "text", "text": "До свидания", "required": False},
    ]
    engine = DialogEngine.from_list(steps)


def test_create_session_and_submit_flow():
    session = engine.create_session()
    assert engine.current_step(session).id == "name"

    step = engine.submit(session, "Alice")
    assert step.id == "age"
    assert session.answers["name"] == "Alice"

    step = engine.submit(session, "30")
    assert step.id == "confirm"
    assert session.answers["age"] == 30

    step = engine.submit(session, "yes")
    assert step.id == "done"
    assert session.answers["confirm"] == "yes"

    step = engine.submit(session, "")
    assert step is None
    assert session.status == SessionStatus.COMPLETED
    assert engine.current_step(session) is None


def test_submit_invalid_value_raises_validation_error():
    session = engine.create_session()
    engine.submit(session, "Alice")
    with pytest.raises(ValidationError):
        engine.submit(session, "not-a-number")


def test_skip_optional_step():
    optional_steps = [
        {"id": "question", "type": "text", "text": "Вопрос", "required": False},
        {"id": "end", "type": "text", "text": "Конец", "required": False},
    ]
    optional_engine = DialogEngine.from_list(optional_steps)
    session = optional_engine.create_session()

    step = optional_engine.skip(session)
    assert step.id == "end"
    assert optional_engine.submit(session, "") is None
    assert session.status == SessionStatus.COMPLETED


def test_skip_required_step_raises():
    session = engine.create_session()
    with pytest.raises(DialogError):
        engine.skip(session)


def test_back_and_jump_to_and_cancel():
    session = engine.create_session()
    engine.submit(session, "Alice")
    engine.submit(session, "30")
    current = engine.current_step(session)
    assert current.id == "confirm"

    previous = engine.back(session)
    assert previous.id == "age"
    assert "age" not in session.answers

    jumped = engine.jump_to(session, "confirm")
    assert jumped.id == "confirm"

    with pytest.raises(StepNotFoundError):
        engine.jump_to(session, "missing")

    engine.cancel(session)
    assert session.is_active is False
    assert engine.current_step(session) is None


def test_resolve_text_uses_custom_resolver():
    custom_engine = DialogEngine.from_list(
        [{"id": "name", "type": "text", "text": "Hello {name}"}],
        text_resolver=lambda text, ctx: text.format(**ctx),
    )
    session = custom_engine.create_session()
    session.answers["name"] = "Alice"
    assert (
        custom_engine.resolve_text(custom_engine.current_step(session), session)
        == "Hello Alice"
    )


def test_restore_session():
    session = engine.create_session()
    engine.submit(session, "Alice")
    session_data = session.to_dict()
    restored = engine.restore_session(session_data)
    assert restored.dialog_id == session.dialog_id
    assert restored._history == session._history
    assert restored.answers == session.answers


def test_from_file_reads_bare_and_wrapped_formats():
    raw_bare = [
        {"id": "a", "type": "text", "text": "A"},
        {"id": "b", "type": "text", "text": "B"},
    ]
    raw_wrapped = {"id": "wrapped", "steps": raw_bare}

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(raw_wrapped, tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name)

    loaded = DialogEngine.from_file(tmp_path)
    assert loaded.dialog_id == "wrapped"
    assert loaded.steps[0].id == "a"
    tmp_path.unlink()
