"""Bundle boundary errors.

Raised only by the (de)serialization entrypoint. Callers catch the ``BundleError``
family rather than pydantic's own ``ValidationError``.
"""


class BundleError(Exception):
    """Base class for all bundle (de)serialization failures."""


class BundleVersionError(BundleError):
    """A bundle's `bundle_version` did not match the current `BUNDLE_SCHEMA_VERSION`."""
