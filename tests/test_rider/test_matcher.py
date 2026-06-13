"""Tests for the rider matcher + mechanical auto-contest."""

from uuid import uuid4

from face_dancer.membrane import recorded_model_calls
from face_dancer.protocol import Delta, EffectOp, ProposeDelta
from face_dancer.rider import Clause, Rider, RiderEffect, Trigger
from face_dancer.rider.matcher import auto_contest, matches


def _clause(
    *,
    tags: set[str],
    op: EffectOp | None = None,
    kind: str = "mechanical",
    claim: str = "x",
    effect: RiderEffect | None = None,
) -> Clause:
    return Clause(
        claim=claim,
        trigger=Trigger(tags=frozenset(tags), op=op),
        kind=kind,  # type: ignore[arg-type]
        source="test",
        effect=effect,
    )


def _propose(*, op: EffectOp = EffectOp.REDUCE, tags: set[str]) -> ProposeDelta:
    return ProposeDelta(correlation_id=uuid4(), delta=Delta(op=op, tags=frozenset(tags)))


# --- matches() ---


def test_op_wildcard_fires_on_any_op() -> None:
    rider = Rider(clauses=[_clause(tags={"fire"}, op=None)])
    assert len(matches(Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"})), rider)) == 1


def test_specific_op_fires_only_on_match() -> None:
    rider = Rider(clauses=[_clause(tags={"fire"}, op=EffectOp.REDUCE)])
    assert matches(Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"})), rider)
    assert matches(Delta(op=EffectOp.SCALE, tags=frozenset({"fire"})), rider) == []


def test_all_tags_must_be_present() -> None:
    rider = Rider(clauses=[_clause(tags={"fire", "magic"})])
    assert matches(Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"})), rider) == []
    assert matches(Delta(op=EffectOp.REDUCE, tags=frozenset({"fire", "magic"})), rider)


def test_returns_mechanical_and_judgment_in_order() -> None:
    rider = Rider(
        clauses=[
            _clause(tags={"fire"}, kind="judgment", claim="argue for a save"),
            _clause(tags={"fire"}, kind="mechanical", claim="resist"),
        ]
    )
    fired = matches(Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"})), rider)
    assert [c.claim for c in fired] == ["argue for a save", "resist"]


def test_no_match_returns_empty() -> None:
    rider = Rider(clauses=[_clause(tags={"cold"})])
    assert matches(Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"})), rider) == []


# --- auto_contest() ---


def test_ac1_mechanical_fire_reduction_makes_no_model_call() -> None:
    rider = Rider(
        clauses=[
            _clause(
                tags={"fire"},
                kind="mechanical",
                claim="I take half from fire",
                effect=RiderEffect(op=EffectOp.SCALE, payload={"factor": 0.5}),
            )
        ]
    )
    propose = _propose(tags={"fire"})
    with recorded_model_calls() as rec:
        contest = auto_contest(propose, rider)
    assert rec.calls == []
    assert contest is not None
    assert contest.correlation_id == propose.correlation_id
    assert len(contest.claims) == 1
    claim = contest.claims[0]
    assert claim.claim == "I take half from fire"
    assert claim.effect is not None
    assert claim.effect.op is EffectOp.SCALE
    assert claim.effect.payload == {"factor": 0.5}


def test_ac8_claim_only_clause_surfaces_as_prose() -> None:
    rider = Rider(clauses=[_clause(tags={"fire"}, kind="mechanical", claim="fire is bad")])
    contest = auto_contest(_propose(tags={"fire"}), rider)
    assert contest is not None
    assert contest.claims[0].effect is None


def test_judgment_clause_excluded_from_contest() -> None:
    rider = Rider(
        clauses=[
            _clause(tags={"fire"}, kind="judgment", claim="argue"),
            _clause(tags={"fire"}, kind="mechanical", claim="resist"),
        ]
    )
    contest = auto_contest(_propose(tags={"fire"}), rider)
    assert contest is not None
    assert [c.claim for c in contest.claims] == ["resist"]


def test_no_mechanical_match_returns_none() -> None:
    judgment_only = Rider(clauses=[_clause(tags={"fire"}, kind="judgment", claim="argue")])
    assert auto_contest(_propose(tags={"fire"}), judgment_only) is None
    assert auto_contest(_propose(tags={"cold"}), Rider()) is None


def test_public_api_is_reexported() -> None:
    import face_dancer.rider as rider

    assert hasattr(rider, "matches")
    assert hasattr(rider, "auto_contest")


def test_empty_trigger_tags_fire_on_everything() -> None:
    # A catch-all: an empty tag-set is a subset of any delta's tags.
    rider = Rider(clauses=[_clause(tags=set(), op=None, kind="mechanical", claim="always")])
    contest = auto_contest(_propose(tags={"anything"}), rider)
    assert contest is not None
    assert contest.claims[0].claim == "always"


def test_multiple_mechanical_clauses_surface_in_order() -> None:
    rider = Rider(
        clauses=[
            _clause(tags={"fire"}, kind="mechanical", claim="first"),
            _clause(tags={"fire"}, kind="mechanical", claim="second"),
        ]
    )
    contest = auto_contest(_propose(tags={"fire"}), rider)
    assert contest is not None
    assert [c.claim for c in contest.claims] == ["first", "second"]
