"""Tests for the protocol version, error hierarchy, and validate() entrypoint."""

from uuid import uuid4

import pytest

from face_dancer.protocol.contest import Claim
from face_dancer.protocol.delta import Delta
from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.messages import (
    ApplyDelta,
    Contest,
    Intent,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.protocol.validation import validate
from face_dancer.protocol.version import SCHEMA_VERSION
from face_dancer.protocol.vocabulary import EffectOp


def test_schema_version_is_a_positive_int() -> None:
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


def test_error_hierarchy() -> None:
    assert issubclass(SchemaVersionError, ProtocolError)
    assert issubclass(UnknownMessageType, ProtocolError)


def test_validate_dispatches_on_discriminator() -> None:
    msg = ProposeDelta(correlation_id=uuid4(), delta=Delta(op=EffectOp.REDUCE))
    parsed = validate(msg.model_dump())
    assert isinstance(parsed, ProposeDelta)
    assert parsed == msg


def test_validate_accepts_json_string() -> None:
    msg = Intent(correlation_id=uuid4(), action="wave")
    parsed = validate(msg.model_dump_json())
    assert isinstance(parsed, Intent)
    assert parsed == msg


def test_validate_rejects_unknown_type() -> None:
    raw = {"type": "teleport", "correlation_id": str(uuid4())}
    with pytest.raises(UnknownMessageType):
        validate(raw)


def test_validate_rejects_wrong_schema_version() -> None:
    raw = {
        "type": "intent",
        "schema_version": SCHEMA_VERSION + 1,
        "correlation_id": str(uuid4()),
        "action": "wave",
    }
    with pytest.raises(SchemaVersionError):
        validate(raw)


def test_validate_wraps_bad_body_as_protocol_error() -> None:
    # `intent` requires an `action`; omitting it is a body error, not a version
    # or discriminator error.
    raw = {"type": "intent", "correlation_id": str(uuid4())}
    with pytest.raises(ProtocolError):
        validate(raw)


def test_validate_wraps_malformed_json() -> None:
    with pytest.raises(ProtocolError) as excinfo:
        validate("{not json")
    assert "malformed JSON" in str(excinfo.value)


def test_validate_rejects_non_dict_json() -> None:
    # This covers the non-dict guard for both dict and string inputs
    with pytest.raises(ProtocolError) as excinfo:
        validate("[1, 2, 3]")
    assert "expected a message object" in str(excinfo.value)


@pytest.mark.parametrize(
    "msg",
    [
        ProposeDelta(
            correlation_id=uuid4(),
            delta=Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"})),
        ),
        ApplyDelta(correlation_id=uuid4(), delta=Delta(op=EffectOp.REDUCE)),
        Contest(correlation_id=uuid4(), claims=[Claim(claim="I have fire resistance")]),
        Intent(correlation_id=uuid4(), action="I drink the potion"),
        RequestRoll(correlation_id=uuid4(), kind="saving_throw", dc=15),
        RollResult(correlation_id=uuid4(), natural=12, modifier=3, total=15),
    ],
)
def test_validate_round_trips_every_message_type(msg) -> None:
    assert validate(msg.model_dump()) == msg
    assert validate(msg.model_dump_json()) == msg


def test_validate_rejects_unknown_delta_op() -> None:
    # delta.op must be a known EffectOp; an unknown op is a body error.
    raw = {
        "type": "propose_delta",
        "correlation_id": str(uuid4()),
        "delta": {"op": "teleport"},
    }
    with pytest.raises(ProtocolError):
        validate(raw)
