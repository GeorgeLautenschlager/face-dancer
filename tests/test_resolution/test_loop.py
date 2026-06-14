"""Tests for the resolution loop: one spine (propose -> contest? -> roll? -> apply)."""

import random
from uuid import UUID, uuid4

import pytest

from face_dancer.membrane import ModelGateway, recorded_model_calls
from face_dancer.protocol import (
    ApplyDelta,
    Contest,
    Delta,
    EffectOp,
    Intent,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.resolution import ResolutionError, ResolutionLoop
from face_dancer.resolution.apply import ApplyError
from face_dancer.rider import Clause, JudgmentAnswer, Rider, RiderEffect, Trigger
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState


class _AffirmingMind(ModelGateway):
    """A stub mind that affirms every judgment question (for route_judgment)."""

    def _invoke(self, request: object) -> object:
        return JudgmentAnswer(applies=True)


class _Session:
    """A scripted, recording Session double.

    ``propose_for_intent`` is returned by adjudicate_intent; ``decision`` by
    adjudicate_propose; ``apply_for_roll`` by adjudicate_roll. It records the
    contest and roll it was handed.
    """

    def __init__(
        self,
        *,
        decision: RequestRoll | ApplyDelta | None = None,
        propose_for_intent: ProposeDelta | None = None,
        apply_for_roll: ApplyDelta | None = None,
    ) -> None:
        self._decision = decision
        self._propose_for_intent = propose_for_intent
        self._apply_for_roll = apply_for_roll
        self.seen_contest: Contest | None = None
        self.seen_contest_set = False
        self.seen_roll: RollResult | None = None

    def adjudicate_intent(self, intent: Intent) -> ProposeDelta:
        assert self._propose_for_intent is not None
        return self._propose_for_intent

    def adjudicate_propose(
        self, propose: ProposeDelta, contest: Contest | None
    ) -> RequestRoll | ApplyDelta:
        self.seen_contest = contest
        self.seen_contest_set = True
        assert self._decision is not None
        return self._decision

    def adjudicate_roll(self, result: RollResult) -> ApplyDelta:
        self.seen_roll = result
        assert self._apply_for_roll is not None
        return self._apply_for_roll


def _loop(
    *,
    rider: Rider | None = None,
    state: DynamicState | None = None,
    sheet: Sheet | None = None,
    gateway: ModelGateway | None = None,
    seed: int = 0,
) -> ResolutionLoop:
    return ResolutionLoop(
        sheet=sheet if sheet is not None else Sheet(),
        rider=rider if rider is not None else Rider(),
        state=state if state is not None else DynamicState(hp=20),
        gateway=gateway if gateway is not None else _AffirmingMind(),
        rng=random.Random(seed),
    )


def _propose(
    cid: UUID, *, target: str = "hp", amount: int = 5, tags: set[str] | None = None
) -> ProposeDelta:
    return ProposeDelta(
        correlation_id=cid,
        delta=Delta(
            op=EffectOp.REDUCE,
            tags=frozenset(tags or set()),
            payload={"target": target, "amount": amount},
        ),
    )


def _apply_delta(cid: UUID, *, target: str = "hp", amount: int = 5) -> ApplyDelta:
    return ApplyDelta(
        correlation_id=cid,
        delta=Delta(
            op=EffectOp.REDUCE, tags=frozenset(), payload={"target": target, "amount": amount}
        ),
    )


def _judgment_clause(*, claim: str, tags: set[str]) -> Clause:
    return Clause(claim=claim, trigger=Trigger(tags=frozenset(tags)), kind="judgment", source="t")


def _mechanical_clause(*, claim: str, tags: set[str], effect: RiderEffect | None = None) -> Clause:
    return Clause(
        claim=claim,
        trigger=Trigger(tags=frozenset(tags)),
        kind="mechanical",
        source="t",
        effect=effect,
    )


# --- AC10: both directions reach apply ---


def test_ac10_inbound_world_caused_reaches_apply() -> None:
    cid = uuid4()
    loop = _loop(state=DynamicState(hp=20))
    session = _Session(decision=_apply_delta(cid, target="hp", amount=5))
    applied = loop.resolve_inbound(_propose(cid, target="hp", amount=5), session)
    assert loop.state.hp == 15
    assert applied.result.hp == 15
    assert applied.result is loop.state


def test_ac10_outbound_self_caused_reaches_apply_same_path() -> None:
    cid = uuid4()
    loop = _loop(state=DynamicState(hp=20, resources={"potion": 3}))
    propose = ProposeDelta(
        correlation_id=cid,
        delta=Delta(
            op=EffectOp.REDUCE,
            tags=frozenset(),
            payload={"target": "resources", "key": "potion", "amount": 1},
        ),
    )
    session = _Session(
        propose_for_intent=propose,
        decision=ApplyDelta(correlation_id=cid, delta=propose.delta),
    )
    applied = loop.resolve_outbound(
        Intent(correlation_id=cid, action="use_item", target="potion"), session
    )
    assert loop.state.resources["potion"] == 2
    assert applied.result.resources["potion"] == 2


# --- contest surfacing ---


def test_mechanical_contest_is_surfaced_to_the_session() -> None:
    cid = uuid4()
    rider = Rider(clauses=[_mechanical_clause(claim="I resist fire", tags={"fire"})])
    loop = _loop(rider=rider)
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert session.seen_contest is not None
    assert [c.claim for c in session.seen_contest.claims] == ["I resist fire"]


def test_judgment_contest_threads_the_gateway() -> None:
    cid = uuid4()
    rider = Rider(clauses=[_judgment_clause(claim="argue for a save", tags={"fire"})])
    loop = _loop(rider=rider)
    session = _Session(decision=_apply_delta(cid))
    with recorded_model_calls() as rec:
        loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert [c.path for c in rec.calls] == ["rider.judgment"]
    assert session.seen_contest is not None
    assert [c.claim for c in session.seen_contest.claims] == ["argue for a save"]


def test_merged_contest_carries_mechanical_and_judgment_claims() -> None:
    cid = uuid4()
    rider = Rider(
        clauses=[
            _mechanical_clause(claim="resist", tags={"fire"}),
            _judgment_clause(claim="argue", tags={"fire"}),
        ]
    )
    loop = _loop(rider=rider)
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert session.seen_contest is not None
    assert {c.claim for c in session.seen_contest.claims} == {"resist", "argue"}


def test_uncontested_calls_adjudicate_propose_with_none() -> None:
    cid = uuid4()
    loop = _loop(rider=Rider())  # empty rider: nothing fires
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert session.seen_contest_set
    assert session.seen_contest is None


# --- roll path ---


def test_roll_path_is_threaded_and_applied() -> None:
    cid = uuid4()
    # sheet gives +3 on the kind; seed 0 -> natural 13 -> total 16
    loop = _loop(
        state=DynamicState(hp=20),
        sheet=Sheet(modifiers={"dexterity_save": 3}),
        seed=0,
    )
    session = _Session(
        decision=RequestRoll(correlation_id=cid, kind="dexterity_save", dc=15),
        apply_for_roll=_apply_delta(cid, target="hp", amount=4),
    )
    loop.resolve_inbound(_propose(cid), session)
    assert session.seen_roll is not None
    assert session.seen_roll.natural == 13
    assert session.seen_roll.total == 16
    assert loop.state.hp == 16  # 20 - 4


# --- guards ---


def test_correlation_mismatch_raises_resolution_error() -> None:
    cid = uuid4()
    loop = _loop()
    session = _Session(decision=_apply_delta(uuid4()))  # wrong correlation_id
    with pytest.raises(ResolutionError):
        loop.resolve_inbound(_propose(cid), session)


def test_correlation_mismatch_after_roll_raises_resolution_error() -> None:
    # The guard sits after the roll branch, so a mismatched apply_delta returned
    # from adjudicate_roll is caught too.
    cid = uuid4()
    loop = _loop()
    session = _Session(
        decision=RequestRoll(correlation_id=cid, kind="dexterity_save", dc=15),
        apply_for_roll=_apply_delta(uuid4()),  # wrong correlation_id
    )
    with pytest.raises(ResolutionError):
        loop.resolve_inbound(_propose(cid), session)


def test_matching_correlation_does_not_raise() -> None:
    cid = uuid4()
    loop = _loop(state=DynamicState(hp=20))
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid), session)  # no raise
    assert loop.state.hp == 15


def test_apply_error_propagates() -> None:
    cid = uuid4()
    loop = _loop()
    bad = ApplyDelta(
        correlation_id=cid, delta=Delta(op=EffectOp.SCALE, tags=frozenset(), payload={})
    )
    session = _Session(decision=bad)
    with pytest.raises(ApplyError):
        loop.resolve_inbound(_propose(cid), session)


# --- model-free apply ---


def test_uncontested_resolution_makes_no_model_call() -> None:
    cid = uuid4()
    loop = _loop(rider=Rider(), state=DynamicState(hp=20))  # empty rider: no judgment routing
    session = _Session(decision=_apply_delta(cid))
    with recorded_model_calls() as rec:
        loop.resolve_inbound(_propose(cid), session)
    assert rec.calls == []


# --- public API ---


def test_public_api_is_reexported() -> None:
    import face_dancer.resolution as resolution

    assert hasattr(resolution, "ResolutionLoop")
    assert hasattr(resolution, "Session")
    assert hasattr(resolution, "ResolutionError")
