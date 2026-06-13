"""The decision policy: route tactical -> code heuristic, expressive -> LLM."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from face_dancer.capability import Capability
from face_dancer.decision.goals import Goals
from face_dancer.membrane import ModelGateway, model_calls_forbidden
from face_dancer.perception import Scene
from face_dancer.protocol import Intent


@dataclass(frozen=True)
class Candidate:
    """A tactical option: a capability aimed at a target (an entity name, or None)."""

    capability: Capability
    target: str | None = None


Scorer = Callable[[Candidate, Scene, Goals], float]


def _first(candidate: Candidate, scene: Scene, goals: Goals) -> float:
    """Trivial default scorer: every candidate scores 0, so max() keeps the first."""
    return 0.0


class DecisionPolicy:
    """Route a decision: tactical -> code heuristic (model-free), expressive -> LLM."""

    def __init__(self, *, gateway: ModelGateway, score: Scorer = _first) -> None:
        self._gateway = gateway
        self._score = score

    def choose_tactical(self, candidates: list[Candidate], scene: Scene, goals: Goals) -> Intent:
        """Select a candidate by the code heuristic, provably without a model call."""
        if not candidates:
            raise ValueError("choose_tactical requires at least one candidate")
        with model_calls_forbidden("tactical decision is code-only"):
            best = max(candidates, key=lambda c: self._score(c, scene, goals))
        return best.capability.to_intent(correlation_id=uuid4(), target=best.target)
