"""The rules-rider schema: reactive, character-known clauses the host may not know."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from face_dancer.protocol import EffectOp


class Trigger(BaseModel):
    """What a clause reacts to: a required tag-set and an optional op wildcard.

    A clause matches a propose_delta when the delta's tags are a superset of
    ``tags`` and, if ``op`` is set, the delta's op equals it. ``op=None`` matches
    any op (one mechanic spanning damage/conditions/saves without enumerating).
    """

    tags: frozenset[str]
    op: EffectOp | None = None


class RiderEffect(BaseModel):
    """A structured reaction the character proposes — drawn from the closed op set.

    Progressive enhancement over ``claim``: a structured host mechanizes this; the
    closed ``EffectOp`` keeps the rider from becoming a rules engine.
    """

    op: EffectOp
    payload: dict[str, Any] = Field(default_factory=dict)


class Clause(BaseModel):
    """One reactive, character-known rule the host may not know.

    Reactive by construction (it requires a ``trigger``); it can encode neither a
    proactive capability nor a static stat — that fence is what keeps the rider
    from becoming a second sheet.
    """

    claim: str
    trigger: Trigger
    kind: Literal["mechanical", "judgment"]
    source: str
    effect: RiderEffect | None = None
    order: int | None = None


class Rider(BaseModel):
    """The character's reactive rules: an ordered set of clauses."""

    clauses: list[Clause] = Field(default_factory=list)
