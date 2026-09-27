"""Шаг confirm: сводка, правка с возвратом, подтверждение."""

import pytest

from dialog_engine import DialogEngine, DialogSession, StepNotFoundError

STEPS = [
    {
        "id": "kind",
        "type": "choice",
        "text": "kind",
        "choices": {"main": "Main", "after": "After"},
        "next": {"main": "title", "after": "guest"},
    },
    {"id": "guest", "type": "text", "text": "guest"},
    {"id": "title", "type": "text", "text": "title"},
    {
        "id": "confirm",
        "type": "confirm",
        "text": "Kind: {kind}\nTitle: {title}\nGuest: {guest}\n{unknown}",
        "choices": {"kind": "Edit kind", "title": "Edit title"},
    },
]


@pytest.fixture
def engine():
    return DialogEngine.from_list(STEPS, dialog_id="upload")


def _to_summary(engine):
    session = engine.create_session()
    engine.submit(session, "main")
    engine.submit(session, "Ep 1")
    return session


def test_summary_filled_with_answers(engine):
    session = _to_summary(engine)
    step = engine.current_step(session)
    assert step.id == "confirm"
    assert engine.resolve_text(step, session) == (
        "Kind: main\nTitle: Ep 1\nGuest: {guest}\n{unknown}"
    )


def test_edit_returns_to_summary(engine):
    session = _to_summary(engine)
    engine.jump_to(session, "title", return_to="confirm")
    assert engine.submit(session, "Ep 2").id == "confirm"
    assert session.return_to is None
    assert "Title: Ep 2" in engine.resolve_text(engine.current_step(session), session)


def test_edit_passes_through_answered_steps(engine):
    session = _to_summary(engine)
    engine.jump_to(session, "kind", return_to="confirm")
    # Та же ветка: title уже отвечен — сразу к сводке.
    assert engine.keep(session).id == "confirm"


def test_edit_opening_new_branch_asks_new_step_first(engine):
    session = _to_summary(engine)
    engine.jump_to(session, "kind", return_to="confirm")
    assert engine.submit(session, "after").id == "guest"
    assert session.return_to == "confirm"
    # title отвечен раньше, поэтому после guest — сразу сводка.
    assert engine.submit(session, "Bob").id == "confirm"


def test_confirm_completes(engine):
    session = _to_summary(engine)
    assert engine.submit(session, True) is None
    assert session.answers["confirm"] is True


def test_back_cancels_return(engine):
    session = _to_summary(engine)
    engine.jump_to(session, "title", return_to="confirm")
    engine.back(session)
    assert session.return_to is None


def test_unknown_return_target(engine):
    session = _to_summary(engine)
    with pytest.raises(StepNotFoundError):
        engine.jump_to(session, "title", return_to="nope")


def test_return_to_serialised(engine):
    session = _to_summary(engine)
    engine.jump_to(session, "title", return_to="confirm")
    assert DialogSession.from_dict(session.to_dict()).return_to == "confirm"
