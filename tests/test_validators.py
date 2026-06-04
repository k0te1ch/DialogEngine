import pytest

from dialog_engine.exceptions import ValidationError
from dialog_engine.step import DialogStep
from dialog_engine.validators import validate


def test_text_validation():
    step = DialogStep(id="name", type="text", text="Name", min=2, max=5)
    assert validate(step, "Alex") == "Alex"
    with pytest.raises(ValidationError):
        validate(step, "A")


def test_text_pattern_fail():
    step = DialogStep(id="code", type="text", text="Code", pattern=r"\d{4}")
    with pytest.raises(ValidationError):
        validate(step, "abc")


def test_optional_text_empty_accepts():
    step = DialogStep(id="note", type="text", text="Note", required=False)
    assert validate(step, "") == ""


def test_number_validation():
    step = DialogStep(id="age", type="number", text="Age", min=1, max=120)
    assert validate(step, "42") == 42
    assert validate(step, "42.0") == 42
    assert validate(step, "42,5") == 42.5
    with pytest.raises(ValidationError):
        validate(step, "abc")


def test_email_validation():
    step = DialogStep(id="email", type="email", text="Email")
    assert validate(step, "USER@Example.COM") == "user@example.com"
    with pytest.raises(ValidationError):
        validate(step, "not-an-email")


def test_boolean_validation():
    step = DialogStep(id="confirm", type="boolean", text="Confirm")
    assert validate(step, "да") is True
    assert validate(step, "no") is False
    with pytest.raises(ValidationError):
        validate(step, "maybe")


def test_choice_validation():
    step = DialogStep(
        id="color",
        type="choice",
        text="Color",
        choices={"R": "Red", "G": "Green"},
    )
    assert validate(step, "G") == "G"
    with pytest.raises(ValidationError):
        validate(step, "B")


def test_multi_choice_validation():
    step = DialogStep(
        id="fruits",
        type="multi_choice",
        text="Fruits",
        choices={"apple": "Apple", "banana": "Banana", "kiwi": "Kiwi"},
        min=1,
        max=2,
    )
    assert validate(step, ["apple", "kiwi"]) == ["apple", "kiwi"]
    assert validate(step, "apple,banana") == ["apple", "banana"]
    with pytest.raises(ValidationError):
        validate(step, "orange")


def test_media_validation():
    photo_step = DialogStep(id="photo", type="photo", text="Photo", min=1, max=2)
    assert validate(photo_step, ["img1"]) == ["img1"]
    with pytest.raises(ValidationError):
        validate(photo_step, [])

    file_step = DialogStep(id="file", type="file", text="File", min=1, max=1)
    assert validate(file_step, "document.pdf") == ["document.pdf"]
    with pytest.raises(ValidationError):
        validate(file_step, ["a.pdf", "b.pdf"])
