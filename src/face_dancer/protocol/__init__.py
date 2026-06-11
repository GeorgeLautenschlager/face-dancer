"""Wire protocol — structured JSON message shapes for the character ↔ host contract.

Messages: propose_delta, contest, apply_delta, intent, request_roll, roll_result.
Markdown/YAML are renders of this data, never the source of truth.
"""

from face_dancer.protocol.envelope import Envelope
from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.messages import (
    MESSAGE_TYPES,
    ApplyDelta,
    Contest,
    Intent,
    Message,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.protocol.validation import export_schema, validate
from face_dancer.protocol.version import SCHEMA_VERSION

__all__ = [
    "MESSAGE_TYPES",
    "SCHEMA_VERSION",
    "ApplyDelta",
    "Contest",
    "Envelope",
    "Intent",
    "Message",
    "ProposeDelta",
    "ProtocolError",
    "RequestRoll",
    "RollResult",
    "SchemaVersionError",
    "UnknownMessageType",
    "export_schema",
    "validate",
]
