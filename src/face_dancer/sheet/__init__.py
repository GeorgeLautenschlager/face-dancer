"""Character sheet — static identity and stats (read-only at runtime).

A system-agnostic base: opaque ``stats`` plus a structured ``modifiers`` contract
the roll engine consumes. System-specific producers (e.g. ``dnd5e``) compute a
Sheet; nothing in the core depends on them.
"""

from face_dancer.sheet.sheet import Sheet

__all__ = ["Sheet"]
