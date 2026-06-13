# Rider Matcher + Mechanical Auto-Contest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the rider matcher (op + tag-set set-comparison) and the model-free mechanical auto-contest that turns fired clauses into a `contest`.

**Architecture:** A single new module `rider/matcher.py` with `matches(delta, rider)` (the pure matcher primitive, returns all firing clauses), `_to_claim(clause)` (progressive enhancement: a clause → a `Claim` with an optional `ClaimEffect`), and `auto_contest(propose, rider)` (mechanical clauses → `Contest | None`, inside a `model_calls_forbidden` region). One task — the module is small and cohesive.

**Tech Stack:** Python 3.11+, pydantic v2 (consumed models), pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-rider-matcher-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **152 passed**.

---

## Task 1: The matcher + mechanical auto-contest

**Files:**
- Create: `src/face_dancer/rider/matcher.py`
- Modify: `src/face_dancer/rider/__init__.py`
- Test: `tests/test_rider/test_matcher.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rider/test_matcher.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_rider/test_matcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.rider.matcher'`.

- [ ] **Step 3: Write the matcher module**

Create `src/face_dancer/rider/matcher.py`:

```python
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
```

- [ ] **Step 4: Re-export from the rider package**

Edit `src/face_dancer/rider/__init__.py` — KEEP the existing module docstring; the
import block and `__all__` become (the `matcher` import sorts before `rider`):

```python
from face_dancer.rider.matcher import auto_contest, matches
from face_dancer.rider.rider import Clause, Rider, RiderEffect, Trigger

__all__ = ["Clause", "Rider", "RiderEffect", "Trigger", "auto_contest", "matches"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_rider/test_matcher.py -v`
Expected: PASS (11 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/rider/matcher.py src/face_dancer/rider/__init__.py tests/test_rider/test_matcher.py
git commit -m "feat(rider): add the matcher + mechanical auto-contest (issue #23)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~163 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from uuid import uuid4
from face_dancer.protocol import Delta, EffectOp, ProposeDelta
from face_dancer.rider import Rider, Clause, Trigger, RiderEffect, auto_contest
from face_dancer.membrane import recorded_model_calls
r = Rider(clauses=[Clause(claim='resist fire', trigger=Trigger(tags=frozenset({'fire'})),
    kind='mechanical', source='race', effect=RiderEffect(op=EffectOp.SCALE, payload={'factor': 0.5}))])
p = ProposeDelta(correlation_id=uuid4(), delta=Delta(op=EffectOp.REDUCE, tags=frozenset({'fire'})))
with recorded_model_calls() as rec:
    c = auto_contest(p, r)
print(c.claims[0].claim, c.claims[0].effect.op.value, rec.calls)
"
# resist fire scale []
```

## Out of scope (do NOT implement)

- Judgment-clause routing to a mind (#25) — `matches` exposes them; do not route them.
- `order`-proposal sequencing; the session's adjudication; request_roll/roll_result.
- The resolution loop (#26) that calls the matcher when a propose_delta arrives.
