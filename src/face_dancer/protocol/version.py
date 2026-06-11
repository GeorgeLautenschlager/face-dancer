"""Schema version and the single change point for the wire protocol.

The wire vocabulary is closed and versioned. To add a message type, append its
class to the ``Message`` union in ``messages.py`` (the one defined place message
types are listed). Bump ``SCHEMA_VERSION`` below only when a change alters the
wire contract a host already speaks -- adding an optional field a host can ignore
need not bump it; adding a required field or a new message type the host must
understand does.

The version is a monotonic integer, not semver: the wire field only needs to
answer "do we speak the same version?", which an integer compares trivially.
"""

SCHEMA_VERSION = 1
