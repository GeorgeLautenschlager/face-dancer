"""The DynamicState model: the character's volatile, code-written state."""

from typing import Any

from pydantic import BaseModel, Field


class DynamicState(BaseModel):
    """The character's volatile, authoritative, code-written state.

    Current HP, active conditions, consumable resources, and an opaque
    host-defined position. Every field is mutated only by code; the model never
    writes here. Max HP and static stats live on the sheet, not here.
    """

    hp: int = 0
    conditions: set[str] = Field(default_factory=set)
    resources: dict[str, int] = Field(default_factory=dict)
    position: dict[str, Any] | None = None
