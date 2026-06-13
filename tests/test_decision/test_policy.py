"""Tests for the decision policy: tactical heuristic + expressive routing."""

from uuid import uuid4

import pytest

from face_dancer.capability import Capability
from face_dancer.decision.goals import Goals
from face_dancer.decision.policy import Candidate, DecisionPolicy
from face_dancer.membrane import ModelCallForbidden, NullModelGateway, recorded_model_calls
from face_dancer.perception import Scene
from face_dancer.protocol import Intent

_FIREBALL = Capability(name="cast fireball", description="hurl flame")
_STRIKE = Capability(name="strike", description="melee")


def _candidates() -> list[Candidate]:
    return [
        Candidate(capability=_STRIKE, target="orc"),
        Candidate(capability=_FIREBALL, target="goblin"),
    ]


def test_tactical_makes_no_model_call() -> None:
    policy = DecisionPolicy(gateway=NullModelGateway())
    with recorded_model_calls() as rec:
        intent = policy.choose_tactical(_candidates(), Scene(), Goals())
    assert rec.calls == []
    assert isinstance(intent, Intent)


def test_tactical_blocks_a_cheating_scorer() -> None:
    gateway = NullModelGateway()

    def cheating_scorer(c: Candidate, s: Scene, g: Goals) -> float:
        gateway.invoke("decision.tactical.cheat", c)
        return 0.0

    policy = DecisionPolicy(gateway=NullModelGateway(), score=cheating_scorer)
    with pytest.raises(ModelCallForbidden):
        policy.choose_tactical(_candidates(), Scene(), Goals())


def test_default_scorer_picks_the_first_candidate() -> None:
    policy = DecisionPolicy(gateway=NullModelGateway())
    intent = policy.choose_tactical(_candidates(), Scene(), Goals())
    assert intent.action == "strike"
    assert intent.target == "orc"
    assert intent.narration is None


def test_injected_scorer_changes_the_choice() -> None:
    policy = DecisionPolicy(
        gateway=NullModelGateway(),
        score=lambda c, s, g: 1.0 if c.target == "goblin" else 0.0,
    )
    intent = policy.choose_tactical(_candidates(), Scene(), Goals())
    assert intent.action == "cast fireball"
    assert intent.target == "goblin"


def test_empty_candidates_raise() -> None:
    policy = DecisionPolicy(gateway=NullModelGateway())
    with pytest.raises(ValueError):
        policy.choose_tactical([], Scene(), Goals())


def test_public_api_is_reexported() -> None:
    import face_dancer.decision as decision

    for name in ("DecisionPolicy", "Candidate", "Scorer", "Goals"):
        assert hasattr(decision, name)


def test_expressive_routes_through_the_gateway() -> None:
    canned = Intent(correlation_id=uuid4(), action="parley", narration="bows low")
    policy = DecisionPolicy(gateway=NullModelGateway(response=canned))
    with recorded_model_calls() as rec:
        result = policy.choose_expressive(Scene(), [_FIREBALL], Goals())
    assert result == canned
    assert [c.path for c in rec.calls] == ["decision.expressive"]


def test_expressive_rejects_a_non_intent_response() -> None:
    policy = DecisionPolicy(gateway=NullModelGateway(response="not an intent"))
    with pytest.raises(TypeError):
        policy.choose_expressive(Scene(), [_FIREBALL], Goals())
