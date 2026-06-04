from dialog_engine.step import DialogStep


def test_from_dict_and_to_dict_roundtrip():
    data = {
        "id": "name",
        "type": "text",
        "text": "Введите имя",
        "required": False,
        "choices": {"A": "Option A"},
        "min": 2,
        "max": 10,
        "pattern": "^[A-Za-z]+$",
        "next": "done",
        "meta": {"hint": "english only"},
    }
    step = DialogStep.from_dict(data)

    assert step.id == "name"
    assert step.type == "text"
    assert step.text == "Введите имя"
    assert step.required is False
    assert step.choices == {"A": "Option A"}
    assert step.min == 2
    assert step.max == 10
    assert step.pattern == "^[A-Za-z]+$"
    assert step.next == "done"
    assert step.meta == {"hint": "english only"}

    serialized = step.to_dict()
    assert serialized["id"] == data["id"]
    assert serialized["type"] == data["type"]
    assert serialized["text"] == data["text"]
    assert serialized["required"] == data["required"]
    assert serialized["choices"] == data["choices"]
    assert serialized["min"] == data["min"]
    assert serialized["max"] == data["max"]
    assert serialized["pattern"] == data["pattern"]
    assert serialized["next"] == data["next"]
    assert serialized["meta"] == data["meta"]


def test_from_dict_supports_legacy_photo_fields():
    data = {
        "id": "photo",
        "type": "photo",
        "text": "Загрузите фото",
        "min_photos": 1,
        "max_photos": 3,
    }
    step = DialogStep.from_dict(data)

    assert step.min == 1
    assert step.max == 3


def test_to_dict_omits_defaults():
    step = DialogStep(
        id="agree",
        type="boolean",
        text="Согласны?",
    )
    assert step.to_dict() == {
        "id": "agree",
        "type": "boolean",
        "text": "Согласны?",
        "required": True,
    }
