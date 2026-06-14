"""Judgment-clause routing: a judgment clause's one question goes to a mind."""

from dataclasses import dataclass

from face_dancer.membrane import ModelGateway
from face_dancer.protocol import Claim, Contest, Delta, ProposeDelta
from face_dancer.rider.matcher import _to_claim, matches
from face_dancer.rider.rider import Rider


@dataclass(frozen=True)
class JudgmentQuestion:
    """The single question a judgment clause raises, handed to the mind.

    ``claim`` is the clause's prose (the question); ``delta`` is the proposed
    change the character is reacting to (context). Crosses the membrane to the
    mind, not the wire — hence a dataclass, not a protocol model.
    """

    claim: str
    delta: Delta


@dataclass(frozen=True)
class JudgmentAnswer:
    """The mind's verdict on a judgment question: does the clause apply?

    Narrow by design — the mind judges applicability; code authors the surfaced
    claim from the clause. ``rationale`` is optional prose the mind may attach.
    """

    applies: bool
    rationale: str | None = None


def route_judgment(propose: ProposeDelta, rider: Rider, gateway: ModelGateway) -> Contest | None:
    """Route each fired judgment clause's question to the mind; contest the affirmed.

    The model-driven twin of ``auto_contest``: it MUST invoke the gateway for each
    judgment clause (never a code verdict). Returns a Contest of the mind-affirmed
    clauses' claims (sharing the propose's correlation_id), or None when no
    judgment clause fires or the mind affirms none.
    """
    fired = [c for c in matches(propose.delta, rider) if c.kind == "judgment"]
    claims: list[Claim] = []
    for clause in fired:
        question = JudgmentQuestion(claim=clause.claim, delta=propose.delta)
        answer = gateway.invoke("rider.judgment", question)
        if not isinstance(answer, JudgmentAnswer):
            raise TypeError(
                f"judgment gateway returned {type(answer).__name__}, expected JudgmentAnswer"
            )
        if answer.applies:
            claims.append(_to_claim(clause))
    if not claims:
        return None
    return Contest(correlation_id=propose.correlation_id, claims=claims)
