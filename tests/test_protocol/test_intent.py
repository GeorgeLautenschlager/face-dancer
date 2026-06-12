"""Tests for the intent message — the character-side opener."""

from uuid import uuid4

import pytest

from face_dancer.protocol.errors import ProtocolError
from face_dancer.protocol.messages import Intent
from face_dancer.protocol.validation import validate


def test_action_only_round_trips() -> None:
    msg = Intent(correlation_id=uuid4(), action="cast fireball")
    assert validate(msg.model_dump()) == msg
    assert validate(msg.model_dump_json()) == msg


def test_full_intent_round_trips() -> None:
    msg = Intent(
        correlation_id=uuid4(),
        action="cast fireball",
        target="goblin",
        narration="With only the barest hint of contempt, Melian hurls a fireball at the goblin.",
    )
    assert validate(msg.model_dump()) == msg
    assert validate(msg.model_dump_json()) == msg


def test_target_and_narration_default_to_none() -> None:
    msg = Intent(correlation_id=uuid4(), action="take cover")
    assert msg.target is None
    assert msg.narration is None


def test_action_is_required() -> None:
    raw = {"type": "intent", "correlation_id": str(uuid4())}
    with pytest.raises(ProtocolError):
        validate(raw)


def test_intent_carries_no_legality_field() -> None:
    # Field-set drift guard: the intent asserts no legality. Adding a legality
    # field (valid/legal/dc/...) must be a deliberate edit that trips this test.
    assert set(Intent.model_fields) == {
        "type",
        "schema_version",
        "message_id",
        "correlation_id",
        "action",
        "target",
        "narration",
    }
