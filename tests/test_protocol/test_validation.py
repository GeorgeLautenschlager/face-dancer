"""Tests for the protocol version, error hierarchy, and validate() entrypoint."""

from uuid import uuid4

import pytest

from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.messages import Intent, ProposeDelta
from face_dancer.protocol.validation import validate
from face_dancer.protocol.version import SCHEMA_VERSION


def test_schema_version_is_a_positive_int() -> None:
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


def test_error_hierarchy() -> None:
    assert issubclass(SchemaVersionError, ProtocolError)
    assert issubclass(UnknownMessageType, ProtocolError)


def test_validate_dispatches_on_discriminator() -> None:
    msg = ProposeDelta(correlation_id=uuid4(), target="self")
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
