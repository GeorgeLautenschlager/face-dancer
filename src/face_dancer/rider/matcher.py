"""The rider matcher: op + tag-set firing, and the code-only mechanical auto-contest."""

from face_dancer.membrane import model_calls_forbidden
from face_dancer.protocol import Claim, ClaimEffect, Contest, Delta, ProposeDelta
from face_dancer.rider.rider import Clause, Rider


def matches(delta: Delta, rider: Rider) -> list[Clause]:
    """Every clause whose trigger fires on this delta (op + tag-set comparison).

    A clause fires when all its trigger tags are present on the delta and its op
    matches (an unset trigger op is a wildcard). Pure; returns mechanical and
    judgment clauses alike, in rider-list order.
    """
    return [
        clause
        for clause in rider.clauses
        if clause.trigger.tags <= delta.tags
        and (clause.trigger.op is None or clause.trigger.op == delta.op)
    ]


def _to_claim(clause: Clause) -> Claim:
    effect = (
        ClaimEffect(op=clause.effect.op, payload=clause.effect.payload)
        if clause.effect is not None
        else None
    )
    return Claim(claim=clause.claim, effect=effect)


def auto_contest(propose: ProposeDelta, rider: Rider) -> Contest | None:
    """Contest the mechanical clauses that fire on a propose_delta, in code.

    Returns a Contest carrying the fired mechanical clauses' claims (sharing the
    propose's correlation_id), or None if none fire. Runs in a model-free region:
    auto-contest never invokes the model.
    """
    with model_calls_forbidden("mechanical auto-contest is code-only"):
        fired = [c for c in matches(propose.delta, rider) if c.kind == "mechanical"]
        if not fired:
            return None
        return Contest(
            correlation_id=propose.correlation_id,
            claims=[_to_claim(c) for c in fired],
        )
