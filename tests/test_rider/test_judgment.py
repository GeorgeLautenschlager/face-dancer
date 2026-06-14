"""Tests for judgment-clause routing: a judgment clause's question goes to a mind."""

from uuid import uuid4

import pytest

from face_dancer.membrane import ModelGateway, recorded_model_calls
from face_dancer.protocol import Delta, EffectOp, ProposeDelta
from face_dancer.rider import (
    Clause,
    JudgmentAnswer,
    JudgmentQuestion,
    Rider,
    RiderEffect,
    Trigger,
    route_judgment,
)


class _Mind(ModelGateway):
    """Test-double mind: returns a per-question result, recording each question.

    ``default`` is returned for any claim not in ``by_claim``. Pass a non-
    JudgmentAnswer ``default`` to exercise the wrong-return-type guard.
    """

    def __init__(self, *, default: object, by_claim: dict[str, object] | None = None) -> None:
        self.seen: list[JudgmentQuestion] = []
        self._default = default
        self._by_claim = by_claim or {}

    def _invoke(self, request: object) -> object:
        assert isinstance(request, JudgmentQuestion)
        self.seen.append(request)
        return self._by_claim.get(request.claim, self._default)


def _judgment_clause(*, claim: str, tags: set[str], effect: RiderEffect | None = None) -> Clause:
    return Clause(
        claim=claim,
        trigger=Trigger(tags=frozenset(tags)),
        kind="judgment",
        source="test",
        effect=effect,
    )


def _mechanical_clause(*, claim: str, tags: set[str]) -> Clause:
    return Clause(
        claim=claim,
        trigger=Trigger(tags=frozenset(tags)),
        kind="mechanical",
        source="test",
    )


def _propose(*, tags: set[str], op: EffectOp = EffectOp.REDUCE) -> ProposeDelta:
    return ProposeDelta(correlation_id=uuid4(), delta=Delta(op=op, tags=frozenset(tags)))


# --- the DoD path: affirmed judgment clause -> contest ---


def test_affirmed_clause_becomes_a_contest_with_its_claim_and_effect() -> None:
    rider = Rider(
        clauses=[
            _judgment_clause(
                claim="this fire ignores my resistance, argue for a save",
                tags={"fire"},
                effect=RiderEffect(op=EffectOp.GRANT_SAVE, payload={"dc": 13}),
            )
        ]
    )
    propose = _propose(tags={"fire"})
    mind = _Mind(default=JudgmentAnswer(applies=True))

    contest = route_judgment(propose, rider, mind)

    assert contest is not None
    assert contest.correlation_id == propose.correlation_id
    assert len(contest.claims) == 1
    claim = contest.claims[0]
    assert claim.claim == "this fire ignores my resistance, argue for a save"
    assert claim.effect is not None
    assert claim.effect.op is EffectOp.GRANT_SAVE
    assert claim.effect.payload == {"dc": 13}
    # the path is model-DRIVEN: the mind was consulted exactly once
    assert len(mind.seen) == 1


def test_one_model_call_recorded_per_judgment_clause() -> None:
    rider = Rider(
        clauses=[
            _judgment_clause(claim="q1", tags={"fire"}),
            _judgment_clause(claim="q2", tags={"fire"}),
        ]
    )
    mind = _Mind(default=JudgmentAnswer(applies=True))
    with recorded_model_calls() as rec:
        route_judgment(_propose(tags={"fire"}), rider, mind)
    assert len(rec.calls) == 2
    assert {c.path for c in rec.calls} == {"rider.judgment"}


# --- decline / empty ---


def test_declined_clause_is_omitted_but_still_routed() -> None:
    rider = Rider(clauses=[_judgment_clause(claim="nope", tags={"fire"})])
    mind = _Mind(default=JudgmentAnswer(applies=False))
    contest = route_judgment(_propose(tags={"fire"}), rider, mind)
    assert contest is None
    assert len(mind.seen) == 1  # the question was still routed to the mind


def test_claim_only_clause_surfaces_as_prose() -> None:
    rider = Rider(clauses=[_judgment_clause(claim="just prose", tags={"fire"})])
    mind = _Mind(default=JudgmentAnswer(applies=True))
    contest = route_judgment(_propose(tags={"fire"}), rider, mind)
    assert contest is not None
    assert contest.claims[0].effect is None


def test_mixed_applies_contests_only_affirmed() -> None:
    rider = Rider(
        clauses=[
            _judgment_clause(claim="yes", tags={"fire"}),
            _judgment_clause(claim="no", tags={"fire"}),
        ]
    )
    mind = _Mind(
        default=JudgmentAnswer(applies=False),
        by_claim={"yes": JudgmentAnswer(applies=True)},
    )
    contest = route_judgment(_propose(tags={"fire"}), rider, mind)
    assert contest is not None
    assert [c.claim for c in contest.claims] == ["yes"]
    assert len(mind.seen) == 2  # both were routed; one affirmed


def test_multiple_affirmed_clauses_surface_in_rider_order() -> None:
    rider = Rider(
        clauses=[
            _judgment_clause(claim="first", tags={"fire"}),
            _judgment_clause(claim="second", tags={"fire"}),
        ]
    )
    mind = _Mind(default=JudgmentAnswer(applies=True))
    contest = route_judgment(_propose(tags={"fire"}), rider, mind)
    assert contest is not None
    assert [c.claim for c in contest.claims] == ["first", "second"]


# --- mechanical clauses are never routed ---


def test_mechanical_clause_is_not_routed() -> None:
    rider = Rider(clauses=[_mechanical_clause(claim="resist", tags={"fire"})])
    mind = _Mind(default=JudgmentAnswer(applies=True))
    contest = route_judgment(_propose(tags={"fire"}), rider, mind)
    assert contest is None
    assert mind.seen == []  # mechanical is auto_contest's job, never the mind's


def test_mixed_rider_routes_only_the_judgment_clause() -> None:
    rider = Rider(
        clauses=[
            _mechanical_clause(claim="resist", tags={"fire"}),
            _judgment_clause(claim="argue", tags={"fire"}),
        ]
    )
    mind = _Mind(default=JudgmentAnswer(applies=True))
    contest = route_judgment(_propose(tags={"fire"}), rider, mind)
    assert contest is not None
    assert [c.claim for c in contest.claims] == ["argue"]
    assert len(mind.seen) == 1


# --- no match ---


def test_no_judgment_match_returns_none_and_makes_no_model_call() -> None:
    rider = Rider(clauses=[_judgment_clause(claim="cold only", tags={"cold"})])
    mind = _Mind(default=JudgmentAnswer(applies=True))
    with recorded_model_calls() as rec:
        contest = route_judgment(_propose(tags={"fire"}), rider, mind)
    assert contest is None
    assert mind.seen == []
    assert rec.calls == []


# --- contract / robustness ---


def test_question_carries_clause_claim_and_delta() -> None:
    rider = Rider(clauses=[_judgment_clause(claim="the question", tags={"fire"})])
    propose = _propose(tags={"fire"})
    mind = _Mind(default=JudgmentAnswer(applies=False))
    route_judgment(propose, rider, mind)
    assert mind.seen[0].claim == "the question"
    assert mind.seen[0].delta == propose.delta


def test_wrong_gateway_return_type_raises_type_error() -> None:
    rider = Rider(clauses=[_judgment_clause(claim="q", tags={"fire"})])
    mind = _Mind(default="not an answer")
    with pytest.raises(TypeError):
        route_judgment(_propose(tags={"fire"}), rider, mind)


def test_public_api_is_reexported() -> None:
    import face_dancer.rider as rider

    assert hasattr(rider, "route_judgment")
    assert hasattr(rider, "JudgmentQuestion")
    assert hasattr(rider, "JudgmentAnswer")
