import pytest

from dialog_engine.exceptions import DialogError
from dialog_engine.step import DialogStep

aiogram_integration = pytest.importorskip(
    "dialog_engine.integrations.aiogram",
    reason="требуется extra aiogram",
)

CallbackParseError = aiogram_integration.CallbackParseError
DialogAction = aiogram_integration.DialogAction
DialogCallback = aiogram_integration.DialogCallback
find_step_by_token = aiogram_integration.find_step_by_token
step_token = aiogram_integration.step_token

LONG_STEP_ID = "выбор_предмета_в_мастере_добавления_домашнего_задания_группы"


def make_step(step_id=LONG_STEP_ID, **kwargs):
    kwargs.setdefault("type", "choice")
    kwargs.setdefault("text", "Выберите предмет")
    return DialogStep(id=step_id, **kwargs)


def test_pack_and_unpack_roundtrip():
    packed = DialogCallback(DialogAction.PICK, step_token("subject"), 7).pack()
    parsed = DialogCallback.unpack(packed)

    assert parsed == DialogCallback(DialogAction.PICK, step_token("subject"), 7)


def test_payload_fits_telegram_limit_for_long_ids():
    step = make_step()
    payload = aiogram_integration.build(DialogAction.PICK, step, 42)

    assert len(payload.encode("utf-8")) <= 64
    assert step.id not in payload


def test_step_token_is_stable_and_distinct():
    assert step_token("subject") == step_token("subject")
    assert step_token("subject") != step_token("deadline")


def test_find_step_by_token():
    steps = [make_step("subject"), make_step("deadline")]

    assert find_step_by_token(steps, step_token("deadline")).id == "deadline"
    assert find_step_by_token(steps, "00000000") is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "",
        "other:p:abc:1",
        "de:p:abc",
        "de:zzz:abc:1",
        "de:p:abc:not-a-number",
    ],
)
def test_unpack_rejects_foreign_payloads(payload):
    with pytest.raises(CallbackParseError):
        DialogCallback.unpack(payload)


def test_parse_error_is_dialog_error():
    assert issubclass(CallbackParseError, DialogError)


def test_pack_rejects_payload_over_limit():
    with pytest.raises(DialogError):
        DialogCallback(DialogAction.PICK, "x" * 100, 1).pack()
