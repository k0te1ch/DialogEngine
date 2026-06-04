from dialog_engine.session import DialogSession, SessionStatus


def test_current_index_and_active_state():
    session = DialogSession(dialog_id="dialog")
    assert session.current_index == 0
    assert session.is_active is True

    session._history = [0, 1]
    assert session.current_index == 1

    session.status = SessionStatus.COMPLETED
    assert session.is_active is False


def test_to_dict_and_from_dict_roundtrip():
    session = DialogSession(dialog_id="dialog")
    session.answers["name"] = "Alice"
    session._history = [0, 1]
    session.status = SessionStatus.CANCELLED

    data = session.to_dict()
    assert data["dialog_id"] == "dialog"
    assert data["answers"] == {"name": "Alice"}
    assert data["history"] == [0, 1]
    assert data["status"] == "cancelled"

    restored = DialogSession.from_dict(data)
    assert restored.dialog_id == "dialog"
    assert restored.answers == {"name": "Alice"}
    assert restored._history == [0, 1]
    assert restored.status == SessionStatus.CANCELLED
