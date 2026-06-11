"""Protocol boundary errors.

Raised only by the validation entrypoint. Callers catch the ``ProtocolError``
family rather than pydantic's own ``ValidationError``.
"""


class ProtocolError(Exception):
    """Base class for all protocol validation failures."""


class SchemaVersionError(ProtocolError):
    """A message's schema_version did not match the current SCHEMA_VERSION."""


class UnknownMessageType(ProtocolError):
    """A message's `type` discriminator matched no known message type."""
