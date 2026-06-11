"""Tests for the protocol version constant and error hierarchy."""

from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.version import SCHEMA_VERSION


def test_schema_version_is_a_positive_int() -> None:
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


def test_error_hierarchy() -> None:
    assert issubclass(SchemaVersionError, ProtocolError)
    assert issubclass(UnknownMessageType, ProtocolError)
