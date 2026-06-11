"""Character bundle — the portable unit a player brings to a game.

Composes sheet (static identity + stats), dynamic state store, and rules rider
into one self-contained, loadable artifact.
"""

from face_dancer.bundle.container import Bundle
from face_dancer.bundle.errors import BundleError, BundleVersionError
from face_dancer.bundle.version import BUNDLE_SCHEMA_VERSION

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "Bundle",
    "BundleError",
    "BundleVersionError",
]
