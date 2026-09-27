"""Перевод ошибок валидации и служебных текстов через резолвер."""

import pytest

from dialog_engine import DialogEngine, ValidationError
from dialog_engine.messages import DEFAULT_MESSAGES

EN = {
    "de.error.text.min": "Too short (at least {min} characters).",
    "de.error.required": "This field is required.",
    "bad.template": "Template does not match",
}

STEPS = [{"id": "name", "type": "text", "text": "name", "min": 3}]


def en_resolver(key, answers, context):
    return EN.get(key, key) if context.get("lang") == "en" else key


def _error(engine, session, value):
    with pytest.raises(ValidationError) as info:
        engine.submit(session, value)
    return info.value


def test_builtin_error_has_key_and_params():
    engine = DialogEngine.from_list(STEPS)
    exc = _error(engine, engine.create_session(), "ab")
    assert exc.key == "de.error.text.min"
    assert exc.params == {"min": 3}
    assert str(exc) == "Слишком короткий текст (минимум 3 символов)."


def test_error_translated_with_params():
    engine = DialogEngine.from_list(STEPS, text_resolver=en_resolver)
    session = engine.create_session(context={"lang": "en"})
    exc = _error(engine, session, "ab")
    assert engine.resolve_error(exc, session) == "Too short (at least 3 characters)."


def test_error_without_translation_keeps_builtin_text():
    engine = DialogEngine.from_list(STEPS, text_resolver=en_resolver)
    session = engine.create_session(context={"lang": "ru"})
    exc = _error(engine, session, "ab")
    assert engine.resolve_error(exc, session) == str(exc)


def test_custom_error_key_is_translated():
    engine = DialogEngine.from_list(STEPS, text_resolver=en_resolver)
    session = engine.create_session(context={"lang": "en"})
    assert (
        engine.resolve_error(ValidationError("bad.template"), session)
        == "Template does not match"
    )
    assert engine.resolve_error(ValidationError("plain text"), session) == "plain text"


def test_resolver_raising_lookup_error_falls_back():
    engine = DialogEngine.from_list(STEPS, text_resolver=lambda key, answers: {}[key])
    assert engine.translate("de.button.back", default="Назад") == "Назад"


def test_broken_placeholder_keeps_translation():
    engine = DialogEngine.from_list(
        STEPS, text_resolver=lambda key, answers: "x {missing}"
    )
    assert engine.translate("k", params={"min": 1}) == "x {missing}"


@pytest.mark.asyncio
async def test_async_resolve_error():
    async def resolver(key, answers, context):
        return EN.get(key, key)

    engine = DialogEngine.from_list(STEPS, text_resolver=resolver)
    session = engine.create_session()
    exc = ValidationError("x", key="de.error.required")
    assert await engine.async_resolve_error(exc, session) == "This field is required."


def test_every_default_message_formats():
    params = {
        "min": 1,
        "max": 2,
        "value": "v",
        "valid": "a",
        "allowed": "a",
        "max_mb": 1,
    }
    for key, template in DEFAULT_MESSAGES.items():
        assert template.format(**params), key
