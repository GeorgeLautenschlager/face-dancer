"""The perceivable-scene payload: a scene of entities with perception gates."""

from pydantic import BaseModel, Field


class PerceptionCheck(BaseModel):
    """A roll-vs-DC gate: the character must beat ``dc`` on a ``kind`` check.

    ``kind`` names the check (e.g. "perception"), resolved later against
    ``sheet.modifier(kind)``; #21 carries it, the roll engine resolves it.
    """

    kind: str
    dc: int


class Entity(BaseModel):
    """A perceivable thing in the scene the character may reference.

    ``perceivable_with`` is the capability gate (perception tags required — empty =
    always perceivable). ``check`` is the optional roll gate. An entity is perceived
    only if both are satisfied.
    """

    name: str
    description: str = ""
    perceivable_with: frozenset[str] = frozenset()
    check: PerceptionCheck | None = None


class Scene(BaseModel):
    """The standard perceivable-scene payload the host sends (session -> character)."""

    description: str = ""
    entities: list[Entity] = Field(default_factory=list)
