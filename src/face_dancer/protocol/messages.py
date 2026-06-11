"""The six wire message types and their discriminated union.

The ``Message`` alias is the single place message types are listed. Adding a
type means adding its class and listing it in ``Message``; ``MESSAGE_TYPES`` is
derived from the union so it can never drift.
"""

from typing import Annotated, Any, Literal, get_args

from pydantic import Field

from face_dancer.protocol.envelope import Envelope


class ProposeDelta(Envelope):
    """Session-proposed change, not yet committed (session -> character)."""

    type: Literal["propose_delta"] = "propose_delta"
    target: str
    tags: frozenset[str] = frozenset()
    effects: list[dict[str, Any]] = Field(default_factory=list)


class ApplyDelta(Envelope):
    """Authoritative change the character's code applies (session -> character).

    Shares ``correlation_id`` with the ``propose_delta`` it finalizes.
    """

    type: Literal["apply_delta"] = "apply_delta"
    target: str
    tags: frozenset[str] = frozenset()
    effects: list[dict[str, Any]] = Field(default_factory=list)


class Contest(Envelope):
    """Character-surfaced claims, not verdicts (character -> session)."""

    type: Literal["contest"] = "contest"
    claims: list[str] = Field(default_factory=list)


class Intent(Envelope):
    """Character-side opener; the session adjudicates it into a propose_delta."""

    type: Literal["intent"] = "intent"
    action: str


class RequestRoll(Envelope):
    """A save or check to resolve (session -> character). DC is session-owned."""

    type: Literal["request_roll"] = "request_roll"
    kind: str
    dc: int | None = None


class RollResult(Envelope):
    """A rolled result; total == natural + modifier, computed in code elsewhere."""

    type: Literal["roll_result"] = "roll_result"
    natural: int
    modifier: int
    total: int


Message = Annotated[
    ProposeDelta | ApplyDelta | Contest | Intent | RequestRoll | RollResult,
    Field(discriminator="type"),
]

# Derived from the union above so the two can never drift. get_args(Message)
# unwraps the Annotated to (<union>, FieldInfo); get_args on that union yields
# the member classes.
MESSAGE_TYPES: tuple[type[Envelope], ...] = get_args(get_args(Message)[0])
