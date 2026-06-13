"""The contest claim shapes: a surfaced rule (claim + optional structured effect).

A contest carries claims, not verdicts: each claim is prose the session reads,
plus an optional structured suggestion. There is no result field — a final number
is unrepresentable here.
"""

from typing import Any

from pydantic import BaseModel, Field

from face_dancer.protocol.vocabulary import EffectOp


class ClaimEffect(BaseModel):
    """A structured suggestion a claim may carry — an op + payload, never a verdict.

    Mirrors the rider's RiderEffect (op from the closed vocabulary, open payload,
    no tags). The session adjudicates it; the contest never asserts a final number.
    """

    op: EffectOp
    payload: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    """One surfaced rule, ~ a matched rider clause: prose plus an optional effect.

    ``claim`` is the mandatory prose a dumb host reads; ``effect`` is the optional
    structured enhancement a host can mechanize. A claim-only Claim is valid.
    """

    claim: str
    effect: ClaimEffect | None = None
