"""The common message envelope shared by every wire message."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from face_dancer.protocol.version import SCHEMA_VERSION


class Envelope(BaseModel):
    """Fields every protocol message carries.

    ``type`` is overridden in each concrete subclass as a ``Literal`` so it can
    serve as the discriminated-union tag. ``schema_version`` defaults to the
    current version for ergonomic outbound construction; strictness lives in
    ``validate()``, which rejects any inbound mismatch.
    """

    type: str
    schema_version: int = SCHEMA_VERSION
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
