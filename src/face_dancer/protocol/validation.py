"""The single validation entrypoint and JSON-Schema export for the protocol."""

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.messages import MESSAGE_TYPES, Message
from face_dancer.protocol.version import SCHEMA_VERSION

_adapter: TypeAdapter[Message] = TypeAdapter(Message)
_VALID_TYPES: frozenset[str] = frozenset(m.model_fields["type"].default for m in MESSAGE_TYPES)


def validate(raw: dict[str, Any] | str) -> Message:
    """Parse and validate a raw message into its concrete typed form.

    Dispatches on the ``type`` discriminator, then enforces ``schema_version``.
    Raises a ``ProtocolError`` subclass on any failure: ``UnknownMessageType``
    for an unrecognised discriminator, ``SchemaVersionError`` for a version
    mismatch, and ``ProtocolError`` for a structurally invalid body.
    """
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"malformed JSON: {exc}") from exc
    else:
        data = raw

    if not isinstance(data, dict):
        raise ProtocolError(f"expected a message object, got {type(data).__name__}")

    type_tag = data.get("type")
    if type_tag not in _VALID_TYPES:
        raise UnknownMessageType(f"unknown message type: {type_tag!r}")

    try:
        msg = _adapter.validate_python(data)
    except ValidationError as exc:
        raise ProtocolError(f"invalid {type_tag} message: {exc}") from exc

    if msg.schema_version != SCHEMA_VERSION:
        raise SchemaVersionError(f"schema_version {msg.schema_version} != current {SCHEMA_VERSION}")
    return msg


def export_schema() -> dict[str, Any]:
    """Return the JSON Schema for the full message union — the published contract."""
    return _adapter.json_schema()


def write_schema(path: Path) -> None:
    """Write the JSON Schema to ``path`` (creating parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export_schema(), indent=2) + "\n")


if __name__ == "__main__":
    write_schema(Path("docs/protocol/schema.json"))
