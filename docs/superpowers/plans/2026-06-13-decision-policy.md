# Decision Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `DecisionPolicy` that routes tactical decisions to a provably model-free code heuristic and expressive decisions through the membrane `ModelGateway`, emitting an `intent`.

**Architecture:** `decision/policy.py` holds `Candidate` (capability + target), an injected `Scorer` (trivial default), and `DecisionPolicy`. `choose_tactical` runs the heuristic inside `model_calls_forbidden` (structural model-free guarantee, AC7) and returns an intent with no narration; `choose_expressive` routes through `ModelGateway.invoke` (a model call is recorded) and returns the adapter's intent. The real scorer, candidate generation, and the model adapter are deferred.

**Tech Stack:** Python 3.11+, pydantic v2 (for the consumed models), stdlib dataclasses, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-decision-policy-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **127 passed**.

---

## Task 1: The tactical path (model-free code heuristic)

**Files:**
- Create: `src/face_dancer/decision/policy.py`
- Modify: `src/face_dancer/decision/__init__.py`
- Test: `tests/test_decision/test_policy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_decision/test_policy.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_decision/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.decision.policy'`.

- [ ] **Step 3: Write the policy module (tactical path)**

Create `src/face_dancer/decision/policy.py`:

```python
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

    def choose_tactical(
        self, candidates: list[Candidate], scene: Scene, goals: Goals
    ) -> Intent:
        """Select a candidate by the code heuristic, provably without a model call."""
        if not candidates:
            raise ValueError("choose_tactical requires at least one candidate")
        with model_calls_forbidden("tactical decision is code-only"):
            best = max(candidates, key=lambda c: self._score(c, scene, goals))
        return best.capability.to_intent(correlation_id=uuid4(), target=best.target)
```

- [ ] **Step 4: Re-export from the decision package**

Edit `src/face_dancer/decision/__init__.py` — KEEP the module docstring and the
existing `Goals` import; the import block and `__all__` become:

```python
from face_dancer.decision.goals import Goals
from face_dancer.decision.policy import Candidate, DecisionPolicy, Scorer

__all__ = ["Candidate", "DecisionPolicy", "Goals", "Scorer"]
```

- [ ] **Step 5: Run the tactical tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_decision/test_policy.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/decision/policy.py src/face_dancer/decision/__init__.py tests/test_decision/test_policy.py
git commit -m "feat(decision): add the model-free tactical decision path (issue #24)"
```

---

## Task 2: The expressive path (route through the model gateway)

**Files:**
- Modify: `src/face_dancer/decision/policy.py`
- Test: `tests/test_decision/test_policy.py`

- [ ] **Step 1: Add the failing expressive tests**

Append to `tests/test_decision/test_policy.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_decision/test_policy.py::test_expressive_routes_through_the_gateway -v`
Expected: FAIL — `AttributeError: 'DecisionPolicy' object has no attribute 'choose_expressive'`.

- [ ] **Step 3: Add `ExpressiveRequest` and `choose_expressive`**

In `src/face_dancer/decision/policy.py`:

(a) Add the `ExpressiveRequest` dataclass directly after `Candidate`:

```python
@dataclass(frozen=True)
class ExpressiveRequest:
    """The opaque request handed to the model on the expressive path (adapter-owned)."""

    scene: Scene
    capabilities: tuple[Capability, ...]
    goals: Goals
```

(b) Add the `choose_expressive` method to `DecisionPolicy` (after `choose_tactical`):

```python
    def choose_expressive(
        self, scene: Scene, capabilities: list[Capability], goals: Goals
    ) -> Intent:
        """Route an expressive decision through the model gateway; return its intent."""
        request = ExpressiveRequest(
            scene=scene, capabilities=tuple(capabilities), goals=goals
        )
        result = self._gateway.invoke("decision.expressive", request)
        if not isinstance(result, Intent):
            raise TypeError(
                f"expressive gateway returned {type(result).__name__}, expected Intent"
            )
        return result
```

- [ ] **Step 4: Run the full decision suite to verify it passes**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_decision -v`
Expected: PASS (8 policy tests + the existing Goals tests).

- [ ] **Step 5: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/decision/policy.py tests/test_decision/test_policy.py
git commit -m "feat(decision): add the expressive path through the model gateway (issue #24)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~135 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from face_dancer.capability import Capability
from face_dancer.decision import DecisionPolicy, Candidate, Goals
from face_dancer.membrane import NullModelGateway, recorded_model_calls
from face_dancer.perception import Scene
cands = [Candidate(capability=Capability(name='strike', description='x'), target='orc'),
         Candidate(capability=Capability(name='cast fireball', description='x'), target='goblin')]
p = DecisionPolicy(gateway=NullModelGateway())
with recorded_model_calls() as rec:
    i = p.choose_tactical(cands, Scene(), Goals())
print(i.action, i.target, i.narration, rec.calls)
"
# strike orc None []
```

## Out of scope (do NOT implement)

- Candidate generation (capability×target applicability); the real tactical scorer.
- The model adapter that resolves the expressive request into an intent (ship the gateway seam + NullModelGateway test double only).
- The resolution spine the emitted intent feeds; the roll engine; the rider matcher; the host side.
