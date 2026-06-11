"""Bundle schema version and the single change point for the bundle format.

The on-disk bundle format is versioned. Bump ``BUNDLE_SCHEMA_VERSION`` below only
when a change alters the persisted contract a stored bundle already speaks --
adding an optional field a loader can default need not bump it; changing the
shape of an existing artifact slot or the container does.

The version is a monotonic integer, not semver: the persisted field only needs to
answer "can this loader read this bundle?", which an integer compares trivially.
This is independent of the protocol's ``SCHEMA_VERSION`` -- the wire and the
on-disk format version separately.
"""

BUNDLE_SCHEMA_VERSION = 1
