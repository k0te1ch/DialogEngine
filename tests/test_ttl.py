"""Срок жизни сессии (ttl)."""

from datetime import timedelta

import pytest

from dialog_engine import DialogEngine, SessionExpiredError

STEPS = [
    {"id": "a", "type": "text", "text": "a"},
    {"id": "b", "type": "text", "text": "b"},
]


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def engine(clock):
    return DialogEngine(
        DialogEngine.from_list(STEPS).steps, dialog_id="d", ttl=60, clock=clock
    )


def test_no_ttl_means_no_expiry():
    session = DialogEngine.from_list(STEPS).create_session()
    assert session.expires_at is None


def test_timedelta_ttl(clock):
    engine = DialogEngine(
        DialogEngine.from_list(STEPS).steps, ttl=timedelta(minutes=2), clock=clock
    )
    assert engine.create_session().expires_at == 1_120.0


def test_each_step_extends_expiry(engine, clock):
    session = engine.create_session()
    assert session.expires_at == 1_060.0
    clock.now += 50
    engine.submit(session, "x")
    assert session.expires_at == 1_110.0
    clock.now += 50
    engine.back(session)
    assert session.expires_at == 1_160.0


def test_expired_session_not_restored_or_advanced(engine, clock):
    session = engine.create_session()
    data = session.to_dict()
    clock.now += 60
    assert engine.is_expired(session)
    assert engine.restore_session(data) is None
    assert engine.restore_session(data, allow_expired=True) is not None
    with pytest.raises(SessionExpiredError):
        engine.submit(session, "x")


def test_from_list_accepts_ttl(clock):
    assert DialogEngine.from_list(STEPS, ttl=5).ttl == 5
