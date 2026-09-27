"""Извлечение метаданных файла из сообщения."""

from types import SimpleNamespace

import pytest

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

message_files = aiogram_integration.message_files


def _message(**fields):
    base = dict.fromkeys(
        ("photo", "document", "audio", "video", "voice", "animation", "video_note")
    )
    return SimpleNamespace(**{**base, **fields})


def test_audio_metadata():
    audio = SimpleNamespace(
        file_id="a", mime_type="audio/mpeg", file_name="ep.mp3", file_size=9
    )
    [info] = message_files(_message(audio=audio))
    assert (info.file_id, info.mime_type, info.file_name, info.file_size) == (
        "a",
        "audio/mpeg",
        "ep.mp3",
        9,
    )


def test_photo_takes_largest_size():
    small = SimpleNamespace(file_id="s", width=90, height=90, file_size=1)
    large = SimpleNamespace(file_id="l", width=1280, height=720, file_size=5)
    [info] = message_files(_message(photo=[small, large]))
    assert info.file_id == "l"
    assert info.mime_type == "image/jpeg"


def test_video_note_without_mime():
    note = SimpleNamespace(file_id="n", file_size=3)
    [info] = message_files(_message(video_note=note))
    assert info.mime_type is None and info.file_name is None


def test_text_message_has_no_files():
    assert message_files(_message()) == []
