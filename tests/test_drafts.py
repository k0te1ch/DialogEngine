"""«Назад» без потери ответа: черновики и keep()."""

import pytest

from dialog_engine import DialogEngine, DialogError, DialogSession

STEPS = [
    {
        "id": "kind",
        "type": "choice",
        "text": "kind",
        "choices": {"a": "A", "b": "B"},
        "next": {"a": "a_detail", "b": "b_detail"},
    },
    {"id": "a_detail", "type": "text", "text": "a", "next": "_end"},
    {"id": "b_detail", "type": "text", "text": "b", "next": "_end"},
]


@pytest.fixture
def engine():
    return DialogEngine.from_list(STEPS, dialog_id="branch")


def test_back_moves_answer_to_draft(engine):
    session = engine.create_session()
    engine.submit(session, "a")
    engine.back(session)
    assert session.answers == {}
    assert engine.draft(session) == "a"


def test_back_then_keep_follows_same_route(engine):
    session = engine.create_session()
    engine.submit(session, "a")
    engine.back(session)
    assert engine.keep(session).id == "a_detail"
    assert session.answers == {"kind": "a"}
    assert session.drafts == {}


def test_back_then_change_takes_new_route(engine):
    session = engine.create_session()
    engine.submit(session, "a")
    engine.back(session)
    assert engine.submit(session, "b").id == "b_detail"
    assert "kind" not in session.drafts


def test_jump_to_keeps_draft(engine):
    session = engine.create_session()
    engine.submit(session, "b")
    engine.jump_to(session, "kind")
    assert engine.draft(session) == "b"


def test_keep_without_draft(engine):
    with pytest.raises(DialogError, match="no previous answer"):
        engine.keep(engine.create_session())


@pytest.mark.asyncio
async def test_async_keep_and_skipped_answer():
    engine = DialogEngine.from_list(
        [
            {"id": "note", "type": "text", "text": "n", "required": False},
            {"id": "end", "type": "text", "text": "e"},
        ]
    )
    session = engine.create_session()
    await engine.async_skip(session)
    await engine.async_back(session)
    assert session.drafts == {"note": None}
    assert (await engine.async_keep(session)).id == "end"
    assert session.answers == {"note": None}


def test_drafts_serialised_and_cleared_on_completion(engine):
    session = engine.create_session()
    engine.submit(session, "a")
    engine.back(session)
    restored = DialogSession.from_dict(session.to_dict())
    assert restored.drafts == {"kind": "a"}

    engine.submit(restored, "b")
    engine.submit(restored, "done")
    assert restored.drafts == {}
