"""Валидатор шага, контекст сессии и резолвер с контекстом."""

import warnings

import pytest

from dialog_engine import DialogEngine, DialogError, DialogSession, ValidationError
from dialog_engine.validators import _ASYNC_VALIDATORS

STEPS = [
    {"id": "kind", "type": "choice", "text": "kind", "choices": {"main": "M"}},
    {"id": "template", "type": "text", "text": "template"},
]


def _engine(**kwargs):
    return DialogEngine.from_list(STEPS, dialog_id="upload", **kwargs)


@pytest.mark.asyncio
async def test_async_validator_normalizes_and_writes_context():
    async def parse(value, ctx):
        ctx.context["number"] = 601
        return {"raw": value, "kind": ctx.answers["kind"]}

    engine = _engine(validators={"template": parse})
    session = engine.create_session()
    await engine.async_submit(session, "main")
    await engine.async_submit(session, "  Title  ")

    assert session.answers["template"] == {"raw": "Title", "kind": "main"}
    assert session.context == {"number": 601}


@pytest.mark.asyncio
async def test_validator_returning_none_keeps_value():
    seen = []
    engine = _engine(validators={"kind": lambda value, ctx: seen.append(ctx.step.id)})
    session = engine.create_session()
    await engine.async_submit(session, "main")
    assert session.answers["kind"] == "main"
    assert seen == ["kind"]


@pytest.mark.asyncio
async def test_validator_error_keeps_step():
    def reject(value, ctx):
        raise ValidationError("bad template", ctx.step.id)

    engine = _engine(validators={"template": reject})
    session = engine.create_session()
    await engine.async_submit(session, "main")
    with pytest.raises(ValidationError, match="bad template"):
        await engine.async_submit(session, "x")
    assert engine.current_step(session).id == "template"
    assert "template" not in session.answers


@pytest.mark.asyncio
async def test_validator_runs_after_builtin_check():
    calls = []
    engine = _engine(validators={"kind": lambda v, ctx: calls.append(v)})
    session = engine.create_session()
    with pytest.raises(ValidationError):
        await engine.async_submit(session, "unknown")
    assert calls == []


def test_sync_submit_with_sync_validator():
    engine = _engine(validators={"kind": lambda v, ctx: v.upper()})
    session = engine.create_session()
    engine.submit(session, "main")
    assert session.answers["kind"] == "MAIN"


def test_sync_submit_rejects_async_validator():
    async def check(value, ctx):
        return value

    engine = _engine(validators={"kind": check})
    session = engine.create_session()
    with pytest.raises(DialogError, match="async_submit"):
        engine.submit(session, "main")


def test_unknown_step_in_validators():
    with pytest.raises(DialogError):
        _engine(validators={"missing": lambda v, ctx: v})


def test_validator_not_serialised():
    engine = _engine(validators={"kind": lambda v, ctx: v})
    assert "validator" not in engine.get_step_by_id("kind").to_dict()


@pytest.mark.asyncio
async def test_legacy_registry_warns_and_step_validator_follows():
    async def legacy(value, step):
        return value.strip() + "!"

    engine = _engine(validators={"template": lambda v, ctx: v + "?"})
    session = engine.create_session()
    await engine.async_submit(session, "main")
    _ASYNC_VALIDATORS["text"] = legacy
    try:
        with pytest.warns(DeprecationWarning):
            await engine.async_submit(session, " hi ")
    finally:
        _ASYNC_VALIDATORS.pop("text")
    assert session.answers["template"] == "hi!?"


# ── Контекст сессии ──────────────────────────────────────────────────────────


def test_context_is_copied_and_serialised():
    start = {"lang": "en"}
    session = _engine().create_session(context=start)
    session.context["n"] = 1
    assert start == {"lang": "en"}

    restored = DialogSession.from_dict(session.to_dict())
    assert restored.context == {"lang": "en", "n": 1}


def test_old_session_without_context():
    restored = DialogSession.from_dict(
        {"dialog_id": "upload", "answers": {}, "history": [0], "status": "in_progress"}
    )
    assert restored.context == {}


# ── Резолвер ─────────────────────────────────────────────────────────────────


def test_resolver_with_context():
    def resolve(key, answers, context):
        return f"{context['lang']}:{key}:{answers.get('kind')}"

    engine = _engine(text_resolver=resolve)
    session = engine.create_session(context={"lang": "en"})
    engine.submit(session, "main")
    step = engine.current_step(session)
    assert engine.resolve_text(step, session) == "en:template:main"


def test_resolver_without_session_gets_empty_context():
    engine = _engine(text_resolver=lambda key, answers, context: f"{key}{context}")
    assert engine.resolve_text(engine.steps[0]) == "kind{}"


def test_two_argument_resolver_still_works():
    engine = _engine(text_resolver=lambda key, answers: key.upper())
    assert engine.resolve_text(engine.steps[0], engine.create_session()) == "KIND"


@pytest.mark.asyncio
async def test_async_resolver_with_context():
    async def resolve(key, answers, context):
        return context["lang"] + key

    engine = _engine(text_resolver=resolve)
    session = engine.create_session(context={"lang": "ru-"})
    assert await engine.async_resolve_text(engine.steps[0], session) == "ru-kind"


def test_no_warning_without_legacy_registry():
    engine = _engine()
    session = engine.create_session()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        engine.submit(session, "main")
