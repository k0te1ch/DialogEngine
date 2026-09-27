"""Ограничения file- и photo-шага: MIME, расширение, размер."""

import pytest

from dialog_engine import DialogEngine, DialogStep, FileInfo, ValidationError

MP3 = {
    "id": "mp3",
    "type": "file",
    "text": "mp3",
    "mime_types": ["audio/*"],
    "extensions": ["MP3"],
    "max_size": 2 * 1024 * 1024,
}

GOOD = FileInfo("f1", mime_type="audio/mpeg", file_name="Ep.MP3", file_size=1024)


def _submit(step_data, value):
    engine = DialogEngine.from_list([step_data])
    session = engine.create_session()
    engine.submit(session, value)
    return session.answers[step_data["id"]]


def test_matching_file_is_stored_as_dict():
    assert _submit(MP3, GOOD) == [GOOD.to_dict()]


def test_dict_answer_accepted():
    assert _submit(MP3, [GOOD.to_dict()]) == [GOOD.to_dict()]


@pytest.mark.parametrize(
    ("info", "key"),
    [
        (FileInfo("f", "video/mp4", "a.mp3", 10), "de.error.media.mime"),
        (FileInfo("f", None, "a.mp3", 10), "de.error.media.mime"),
        (FileInfo("f", "audio/mpeg", "a.wav", 10), "de.error.media.extension"),
        (FileInfo("f", "audio/mpeg", "noext", 10), "de.error.media.extension"),
        (FileInfo("f", "audio/mpeg", "a.mp3", 3 * 1024 * 1024), "de.error.media.size"),
        (FileInfo("f", "audio/mpeg", "a.mp3", None), "de.error.media.size"),
        ("bare_file_id", "de.error.media.mime"),
    ],
)
def test_rejected_files(info, key):
    with pytest.raises(ValidationError) as exc:
        _submit(MP3, info)
    assert exc.value.key == key


def test_size_message():
    with pytest.raises(ValidationError, match="максимум 2 МБ"):
        _submit(MP3, FileInfo("f", "audio/mpeg", "a.mp3", 3 * 1024 * 1024))


def test_without_constraints_answer_stays_file_ids():
    plain = {"id": "doc", "type": "file", "text": "doc"}
    assert _submit(plain, "file_id") == ["file_id"]
    assert _submit(plain, GOOD) == ["f1"]


def test_constraints_round_trip():
    step = DialogStep.from_dict(MP3)
    assert step.has_file_constraints
    assert DialogStep.from_dict(step.to_dict()) == step
