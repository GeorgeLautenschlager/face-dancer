# Judgment-Clause Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `route_judgment(propose, rider, gateway) -> Contest | None` — the model-driven twin of `auto_contest`: it routes each fired `judgment` clause's one question to the character's mind (a `ModelGateway`) and contests the clauses the mind affirms.

**Architecture:** One new leaf module `rider/judgment.py` with two frozen dataclasses (`JudgmentQuestion`, `JudgmentAnswer`) and `route_judgment`, re-exported from `rider/__init__.py`. It reuses `matches` and the canonical `_to_claim` mapping from `rider/matcher.py`. Unlike `auto_contest` it is structurally model-*driven* — it must invoke the gateway per judgment clause (never a code verdict). One task — the module is small and cohesive.

**Tech Stack:** Python 3.11+, pydantic v2 (consumed models), dataclasses (stdlib), pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-14-judgment-routing-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **187 passed**.

Reference shapes (already on this base):
- `Clause(claim: str, trigger: Trigger, kind: Literal["mechanical","judgment"], source: str, effect: RiderEffect | None = None, order: int | None = None)`
- `Trigger(tags: frozenset[str], op: EffectOp | None = None)`; `RiderEffect(op: EffectOp, payload: dict = {})`
- `matches(delta, rider) -> list[Clause]` and the private `_to_claim(clause) -> Claim` live in `face_dancer.rider.matcher`.
- `ModelGateway` is abstract: subclasses implement `_invoke(self, request) -> object`; the `@final` `invoke(path, request)` records a `ModelCall` then delegates. Subclasses may NOT override `invoke`.

---

## Task 1: The judgment router (`rider/judgment.py`)

**Files:**
- Create: `src/face_dancer/rider/judgment.py`
- Modify: `src/face_dancer/rider/__init__.py`
- Test: `tests/test_rider/test_judgment.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rider/test_judgment.py`:

```python
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

    def __init__(
        self, *, default: object, by_claim: dict[str, object] | None = None
    ) -> None:
        self.seen: list[JudgmentQuestion] = []
        self._default = default
        self._by_claim = by_claim or {}

    def _invoke(self, request: object) -> object:
        assert isinstance(request, JudgmentQuestion)
        self.seen.append(request)
        return self._by_claim.get(request.claim, self._default)


def _judgment_clause(
    *, claim: str, tags: set[str], effect: RiderEffect | None = None
) -> Clause:
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
    return ProposeDelta(
        correlation_id=uuid4(), delta=Delta(op=op, tags=frozenset(tags))
    )


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_rider/test_judgment.py -v`
Expected: FAIL — `ImportError: cannot import name 'route_judgment' from 'face_dancer.rider'` (the module does not exist yet).

- [ ] **Step 3: Write the judgment router module**

Create `src/face_dancer/rider/judgment.py`:

```python
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


def route_judgment(
    propose: ProposeDelta, rider: Rider, gateway: ModelGateway
) -> Contest | None:
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
                f"judgment gateway returned {type(answer).__name__}, "
                "expected JudgmentAnswer"
            )
        if answer.applies:
            claims.append(_to_claim(clause))
    if not claims:
        return None
    return Contest(correlation_id=propose.correlation_id, claims=claims)
```

- [ ] **Step 4: Re-export from the rider package**

Edit `src/face_dancer/rider/__init__.py` — KEEP the existing module docstring. The
import block and `__all__` become (imports sorted: `judgment` before `matcher`
before `rider`; `__all__` kept alphabetical):

```python
from face_dancer.rider.judgment import JudgmentAnswer, JudgmentQuestion, route_judgment
from face_dancer.rider.matcher import auto_contest, matches
from face_dancer.rider.rider import Clause, Rider, RiderEffect, Trigger

__all__ = [
    "Clause",
    "JudgmentAnswer",
    "JudgmentQuestion",
    "Rider",
    "RiderEffect",
    "Trigger",
    "auto_contest",
    "matches",
    "route_judgment",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_rider/test_judgment.py -v`
Expected: PASS (11 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/rider/judgment.py src/face_dancer/rider/__init__.py tests/test_rider/test_judgment.py
git commit -m "feat(rider): add judgment-clause routing to a mind (issue #25)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~198 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from uuid import uuid4
from face_dancer.membrane import ModelGateway, recorded_model_calls
from face_dancer.protocol import Delta, EffectOp, ProposeDelta
from face_dancer.rider import Clause, Rider, RiderEffect, Trigger, JudgmentAnswer, JudgmentQuestion, route_judgment

class Mind(ModelGateway):
    def _invoke(self, request): return JudgmentAnswer(applies=True)

rider = Rider(clauses=[Clause(claim='argue for a save', trigger=Trigger(tags=frozenset({'fire'})),
    kind='judgment', source='gm-ruling', effect=RiderEffect(op=EffectOp.GRANT_SAVE, payload={'dc': 13}))])
p = ProposeDelta(correlation_id=uuid4(), delta=Delta(op=EffectOp.REDUCE, tags=frozenset({'fire'})))
with recorded_model_calls() as rec:
    c = route_judgment(p, rider, Mind())
print(c.claims[0].claim, c.claims[0].effect.op.value, [call.path for call in rec.calls])
"
# argue for a save grant_save ['rider.judgment']
```

## Out of scope (do NOT implement)

- **Punt-to-host** routing and **host-capability detection** — a later
  `ModelGateway` adapter; the #5 spike defers them.
- The **real `ModelGateway` adapter** (the character's actual model) — a brief
  non-goal; tests use a double.
- The **resolution loop** (#26) that calls `route_judgment` and adjudicates the
  emitted `Contest`; `order`-proposal sequencing of claims.
- Any change to `auto_contest`, the matcher, or the wire protocol/schema.
