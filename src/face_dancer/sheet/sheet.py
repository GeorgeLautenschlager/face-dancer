"""The generic, read-only character sheet: opaque stats + a modifier contract."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Sheet(BaseModel):
    """The character's static, read-only sheet: opaque stats + a modifier contract.

    ``stats`` is the host/system-defined stat block (ability scores, max HP, AC,
    proficiencies — whatever the system uses); the character carries it but the
    core never interprets it. ``modifiers`` is the structured contract the roll
    engine consumes via ``modifier()``. The sheet is frozen — read-only at runtime.
    """

    model_config = ConfigDict(frozen=True)

    stats: dict[str, Any] = Field(default_factory=dict)
    modifiers: dict[str, int] = Field(default_factory=dict)

    def modifier(self, kind: str) -> int:
        """Return the modifier the roll engine should apply for ``kind`` (0 if absent)."""
        return self.modifiers.get(kind, 0)
