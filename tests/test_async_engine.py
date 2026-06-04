"""Tests for async operations in DialogEngine."""

import pytest

from dialog_engine import DialogEngine
from dialog_engine.exceptions import DialogError
from dialog_engine.session import SessionStatus


@pytest.fixture
def engine():
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
    return DialogEngine.from_list(steps)


@pytest.mark.asyncio
async def test_async_submit_flow(engine):
    """Test async submit flow."""
    session = engine.create_session()
    assert engine.current_step(session).id == "name"

    step = await engine.async_submit(session, "Alice")
    assert step.id == "age"
    assert session.answers["name"] == "Alice"

    step = await engine.async_submit(session, "30")
    assert step.id == "confirm"
    assert session.answers["age"] == 30

    step = await engine.async_submit(session, "yes")
    assert step.id == "done"
    assert session.answers["confirm"] == "yes"

    step = await engine.async_submit(session, "")
    assert step is None
    assert session.status == SessionStatus.COMPLETED
    assert engine.current_step(session) is None


@pytest.mark.asyncio
async def test_async_skip_optional_step():
    """Test async skip of optional step."""
    optional_steps = [
        {"id": "question", "type": "text", "text": "Вопрос", "required": False},
        {"id": "end", "type": "text", "text": "Конец", "required": False},
    ]
    optional_engine = DialogEngine.from_list(optional_steps)
    session = optional_engine.create_session()

    step = await optional_engine.async_skip(session)
    assert step.id == "end"
    assert await optional_engine.async_submit(session, "") is None
    assert session.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_async_skip_required_step_raises(engine):
    """Test that async skip of required step raises error."""
    session = engine.create_session()
    with pytest.raises(DialogError):
        await engine.async_skip(session)


@pytest.mark.asyncio
async def test_async_back(engine):
    """Test async back operation."""
    session = engine.create_session()
    await engine.async_submit(session, "Alice")
    await engine.async_submit(session, "30")
    current = engine.current_step(session)
    assert current.id == "confirm"

    previous = await engine.async_back(session)
    assert previous.id == "age"
    assert "age" not in session.answers


@pytest.mark.asyncio
async def test_async_resolve_text_with_sync_resolver(engine):
    """Test async resolve_text with sync resolver."""
    session = engine.create_session()
    await engine.async_submit(session, "Alice")
    step = engine.current_step(session)
    text = await engine.async_resolve_text(step, session)
    assert text == "Ваш возраст?"


@pytest.mark.asyncio
async def test_async_resolve_text_with_async_resolver():
    """Test async resolve_text with async resolver."""

    async def async_resolver(text: str, ctx: dict):
        return text.format(**ctx)

    custom_engine = DialogEngine.from_list(
        [{"id": "name", "type": "text", "text": "Hello {name}!"}],
        text_resolver=async_resolver,
    )
    session = custom_engine.create_session()
    session.answers["name"] = "Alice"
    step = custom_engine.current_step(session)
    text = await custom_engine.async_resolve_text(step, session)
    assert text == "Hello Alice!"


@pytest.mark.asyncio
async def test_sync_methods_work_without_async_validator(engine):
    """Test that sync methods work correctly when no async validator is used."""
    # This test verifies that sync methods work as expected with sync validation

    # Test submit
    session = engine.create_session()
    step = engine.submit(session, "Alice")
    assert step.id == "age"
    assert session.answers["name"] == "Alice"

    # Test skip
    optional_steps = [
        {"id": "question", "type": "text", "text": "Вопрос", "required": False},
        {"id": "end", "type": "text", "text": "Конец", "required": False},
    ]
    optional_engine = DialogEngine.from_list(optional_steps)
    session = optional_engine.create_session()
    step = optional_engine.skip(session)
    assert step.id == "end"

    # Test back
    session = engine.create_session()
    engine.submit(session, "Alice")
    engine.submit(session, "30")
    previous = engine.back(session)
    assert previous.id == "age"
    assert "age" not in session.answers

    # Test resolve_text with async resolver - should raise error
    async def async_resolver(text: str, ctx: dict):
        return text

    async_engine = DialogEngine.from_list(
        [{"id": "test", "type": "text", "text": "Test"}],
        text_resolver=async_resolver,
    )
    session = async_engine.create_session()
    with pytest.raises(
        DialogError, match="Async text resolver requires calling async_resolve_text"
    ):
        async_engine.resolve_text(async_engine.current_step(session), session)
