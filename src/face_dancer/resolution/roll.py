"""The roll engine: code rolls the die and applies the character's modifier."""

import random

from face_dancer.membrane import model_calls_forbidden
from face_dancer.protocol import EffectOp, RequestRoll, RollResult
from face_dancer.rider import Rider
from face_dancer.sheet import Sheet


def _rider_bonus(kind: str, rider: Rider) -> int:
    """Sum flat MODIFY_ROLL bonuses whose trigger fires on a roll of this kind.

    A clause contributes when it carries a MODIFY_ROLL effect and its trigger tags
    are a subset of the roll's single-tag set ``{kind}``. The roll has no op, so
    ``trigger.op`` is not consulted; a non-flat (advantage) payload contributes 0.
    """
    roll_tags = {kind}
    total = 0
    for clause in rider.clauses:
        effect = clause.effect
        if (
            effect is not None
            and effect.op is EffectOp.MODIFY_ROLL
            and clause.trigger.tags <= roll_tags
        ):
            total += effect.payload.get("bonus", 0)
    return total


def roll(
    request: RequestRoll,
    sheet: Sheet,
    rider: Rider,
    *,
    rng: random.Random | None = None,
) -> RollResult:
    """Resolve a request_roll into a roll_result, model-free.

    Rolls a d20 and applies the character's own modifier (sheet + rider). The
    returned RollResult shares the request's correlation_id and satisfies
    ``total == natural + modifier``. Pass a seeded ``rng`` for deterministic tests.
    """
    rng = rng if rng is not None else random.Random()
    with model_calls_forbidden("roll engine is code-only"):
        natural = rng.randint(1, 20)
        modifier = sheet.modifier(request.kind) + _rider_bonus(request.kind, rider)
        return RollResult(
            correlation_id=request.correlation_id,
            natural=natural,
            modifier=modifier,
            total=natural + modifier,
        )
