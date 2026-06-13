# Decision Policy — Tactical Heuristic vs. Expressive LLM Routing

**Issue:** [#24](https://github.com/GeorgeLautenschlager/face-dancer/issues/24)
**Date:** 2026-06-13
**Status:** Approved

## Purpose

Brief §3 — the decision step is split: **tactical** choices (targeting, move
selection) run at a faster pace than **expressive** choices (speech, social and
moral beats). v0 targets turn-based games and routes both through the membrane;
the **tactical path uses a code heuristic** so the scarce model isn't burned on
routine selection. The chosen action leaves as an `intent`. This is the fourth
instance of the #8 membrane (model proposes, code disposes).

This issue builds the decision policy: route tactical → code heuristic (provably
model-free), expressive → LLM (via the membrane `ModelGateway`; the adapter is a
non-goal), consuming perception (#21) and capabilities/goals (#22), emitting an
`intent` (#13).

## Decisions

- **Tactical selection is an injected scorer with a trivial default.** The policy
  selects the argmax candidate via `score: Callable[[Candidate, Scene, Goals],
  float]`, shipping a trivial default `_first` (constant → picks the first
  candidate stably, deterministically). The policy owns the selection seam; a
  smarter heuristic drops in later without touching the routing. The scoring
  *intelligence* is deferred (goals are prose a code heuristic can't deeply reason
  over); #24's deliverable is the routing + the model-free guarantee + the seam.

- **The tactical path is structurally model-free, not merely tested.** `choose_
  tactical` runs the heuristic inside the membrane's `model_calls_forbidden(...)`
  region, so even a misbehaving scorer that tried to invoke the model **raises**
  `ModelCallForbidden`. AC7 ("selects one via the code heuristic with no model
  call") is a structural property of the path, mirroring how `dispose()` runs in a
  model-free region.

- **The expressive path routes through the membrane `ModelGateway`.** `choose_
  expressive` calls `gateway.invoke("decision.expressive", request)`, so a model
  call **is** recorded — the mirror of the tactical guarantee. The LLM produces the
  `intent` (with `narration`). The real adapter is deferred (brief non-goal);
  v0/tests inject `NullModelGateway(response=Intent(...))`.

- **Tactical intents carry no `narration`; expressive intents do.** Tactical is
  mechanical (action + target); the expressive flair (#13's `narration`) is the
  LLM's to write. This reinforces the split.

- **A `Candidate` is a `(capability, target)` pair.** `Candidate(capability:
  Capability, target: str | None)` — what to do and on whom (an entity name from
  the scoped `Scene`). The chosen candidate becomes an intent via
  `capability.to_intent(...)`, which mints a fresh `correlation_id` (an intent
  opens an outbound exchange, per #9).

- **The policy *selects* among given candidates; it does not generate them.** AC7
  is "given two candidate tactical actions, select one." Candidate **generation**
  (capability×target applicability — fireball targets enemies, heal targets
  allies) is non-trivial and deferred to its own concern.

- **Both paths are goal-aware** (the brief: goals bias the decision at three
  timescales). The default scorer receives `Goals` but ignores them; the expressive
  request carries them for the adapter.

## Architecture

New module in the existing `decision/` package (which already holds `Goals`).

```
src/face_dancer/decision/
├── __init__.py     # re-exports Goals (existing) + DecisionPolicy, Candidate, Scorer
├── goals.py        # (existing)
└── policy.py       # NEW: Candidate, ExpressiveRequest, Scorer, DecisionPolicy
```

Dependency direction: `policy.py` imports `Capability` (`face_dancer.capability`),
`Scene` (`face_dancer.perception`), `Goals` (`face_dancer.decision.goals`),
`Intent` (`face_dancer.protocol`), and `ModelGateway` / `model_calls_forbidden`
(`face_dancer.membrane`). No cycles.

## The decision policy (`decision/policy.py`)

```python
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


@dataclass(frozen=True)
class ExpressiveRequest:
    """The opaque request handed to the model on the expressive path (adapter-owned)."""

    scene: Scene
    capabilities: tuple[Capability, ...]
    goals: Goals


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

    def choose_expressive(
        self, scene: Scene, capabilities: list[Capability], goals: Goals
    ) -> Intent:
        """Route an expressive decision through the model gateway; return its intent."""
        request = ExpressiveRequest(scene=scene, capabilities=tuple(capabilities), goals=goals)
        result = self._gateway.invoke("decision.expressive", request)
        if not isinstance(result, Intent):
            raise TypeError(f"expressive gateway returned {type(result).__name__}, expected Intent")
        return result
```

Re-exported from `decision/__init__.py` (keep the docstring + the existing `Goals`
export): `Candidate`, `DecisionPolicy`, `Goals`, `Scorer`.

## Testing

`tests/test_decision/test_policy.py`:

1. **AC7 — tactical selection is model-free:** within `recorded_model_calls()`,
   `choose_tactical([c1, c2], scene, goals)` returns one candidate's intent and the
   recorder is **empty** (no model call).
2. **Structural guarantee:** a scorer that calls a gateway inside scoring causes
   `choose_tactical` to raise `ModelCallForbidden`.
3. **Injected scorer changes the choice:** with `score=lambda c, s, g: 1.0 if
   c.target == "goblin" else 0.0`, the goblin candidate is chosen; the default
   `_first` picks the first.
4. **Tactical intent has no narration:** the returned `Intent.narration is None`
   and `action == chosen.capability.name`, `target == chosen.target`.
5. **Empty candidates raise `ValueError`.**
6. **Expressive routes through the gateway:** with
   `NullModelGateway(response=Intent(...))`, `choose_expressive(...)` returns that
   intent, and within `recorded_model_calls()` the recorder has **one** call on
   path `"decision.expressive"`.
7. **Expressive rejects a non-Intent response:** `NullModelGateway(response="x")`
   makes `choose_expressive` raise `TypeError`.
8. **Public API:** `face_dancer.decision` re-exports `DecisionPolicy`, `Candidate`,
   `Scorer`, `Goals`.

`tests/test_decision/test_goals.py` already exists; the package `__init__.py` is
present. All code passes `mypy --strict` and the existing ruff config.

## Out of scope

- **Candidate generation** (capability×target applicability) — its own concern.
- **The real tactical scorer** — the default is trivial; a meaningful heuristic is
  later.
- **The model adapter** that resolves the expressive request into an intent (brief
  non-goal) — #24 ships the gateway seam and the `NullModelGateway` test double.
- **The resolution spine** (propose → contest? → apply) the emitted intent feeds.
- The **roll engine**, the rider matcher, the host side.
