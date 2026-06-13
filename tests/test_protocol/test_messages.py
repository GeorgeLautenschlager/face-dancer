"""Round-trip and envelope-default tests for the six message types."""

from typing import Any
from uuid import UUID, uuid4

import pytest

from face_dancer.protocol.contest import Claim
from face_dancer.protocol.delta import Delta
from face_dancer.protocol.messages import (
    MESSAGE_TYPES,
    ApplyDelta,
    Contest,
    Intent,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.protocol.version import SCHEMA_VERSION
from face_dancer.protocol.vocabulary import EffectOp


def _one_of_each() -> list[Any]:
    cid = uuid4()
    return [
        ProposeDelta(
            correlation_id=cid,
            delta=Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"}), payload={"amount": 8}),
        ),
        ApplyDelta(
            correlation_id=cid,
            delta=Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"}), payload={"amount": 4}),
        ),
        Contest(correlation_id=cid, claims=[Claim(claim="I have fire resistance and a save")]),
        Intent(correlation_id=uuid4(), action="I drink the potion"),
        RequestRoll(correlation_id=cid, kind="saving_throw", dc=15),
        RollResult(correlation_id=cid, natural=12, modifier=3, total=15),
    ]


@pytest.mark.parametrize("msg", _one_of_each())
def test_round_trip_through_python(msg: Any) -> None:
    rebuilt = type(msg).model_validate(msg.model_dump())
    assert rebuilt == msg


@pytest.mark.parametrize("msg", _one_of_each())
def test_round_trip_through_json(msg: Any) -> None:
    rebuilt = type(msg).model_validate_json(msg.model_dump_json())
    assert rebuilt == msg


def test_message_id_defaults_to_unique_uuid() -> None:
    a = Intent(correlation_id=uuid4(), action="wave")
    b = Intent(correlation_id=uuid4(), action="wave")
    assert isinstance(a.message_id, UUID)
    assert a.message_id != b.message_id


def test_schema_version_defaults_to_current() -> None:
    msg = Intent(correlation_id=uuid4(), action="wave")
    assert msg.schema_version == SCHEMA_VERSION


def test_message_types_registry_has_all_six() -> None:
    assert set(MESSAGE_TYPES) == {
        ProposeDelta,
        ApplyDelta,
        Contest,
        Intent,
        RequestRoll,
        RollResult,
    }


def test_public_api_is_reexported() -> None:
    import face_dancer.protocol as protocol

    for name in (
        "Message",
        "Envelope",
        "ProposeDelta",
        "ApplyDelta",
        "Contest",
        "Intent",
        "RequestRoll",
        "RollResult",
        "MESSAGE_TYPES",
        "SCHEMA_VERSION",
        "validate",
        "export_schema",
        "ProtocolError",
        "SchemaVersionError",
        "UnknownMessageType",
    ):
        assert hasattr(protocol, name), f"protocol package does not re-export {name}"
