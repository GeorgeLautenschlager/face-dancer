# Roll Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the model-free roll engine: `roll(request, sheet, rider, *, rng=None) -> RollResult` rolls a d20 and applies the character's modifier (sheet + rider `MODIFY_ROLL` clauses), producing a `roll_result` whose `total == natural + modifier`.

**Architecture:** One new leaf module `resolution/roll.py` with a private `_rider_bonus` helper and the public `roll` function, re-exported from `resolution/__init__.py`. The whole computation runs inside the membrane's `model_calls_forbidden` region (AC5). A seedable injected `random.Random` makes it deterministically testable (AC4). One task — the module is small and cohesive.

**Tech Stack:** Python 3.11+, pydantic v2 (consumed models), `random` (stdlib), pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-14-roll-engine-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **171 passed**.

Two facts the tests below rely on:
- `random.Random(0).randint(1, 20) == 13` (the pinned deterministic natural roll).
- `Sheet(modifiers={...}).modifier(kind)` returns the int for `kind`, or `0` if absent.

---

## Task 1: The roll engine (`resolution/roll.py`)

**Files:**
- Create: `src/face_dancer/resolution/roll.py`
- Modify: `src/face_dancer/resolution/__init__.py`
- Test: `tests/test_resolution/test_roll.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resolution/test_roll.py`:

```python
"""Tests for the roll engine: code rolls the d20 and applies the modifier."""

import random
from uuid import uuid4

import pytest

from face_dancer.membrane import (
    ModelCallForbidden,
    ModelGateway,
    recorded_model_calls,
)
from face_dancer.protocol import EffectOp, RequestRoll, RollResult
from face_dancer.resolution import roll
from face_dancer.rider import Clause, Rider, RiderEffect, Trigger
from face_dancer.sheet import Sheet


def _request(kind: str = "perception", dc: int | None = None) -> RequestRoll:
    return RequestRoll(correlation_id=uuid4(), kind=kind, dc=dc)


def _modify_roll_clause(
    *, tags: set[str], bonus: int | None = None, op: EffectOp = EffectOp.MODIFY_ROLL
) -> Clause:
    payload: dict[str, int] = {} if bonus is None else {"bonus": bonus}
    return Clause(
        claim="roll modifier",
        trigger=Trigger(tags=frozenset(tags)),
        kind="mechanical",
        source="test",
        effect=RiderEffect(op=op, payload=payload),
    )


# --- determinism / arithmetic (AC4) ---


def test_seeded_roll_is_deterministic_natural_13() -> None:
    # random.Random(0).randint(1, 20) == 13
    result = roll(_request(), Sheet(), Rider(), rng=random.Random(0))
    assert result.natural == 13
    assert result.modifier == 0
    assert result.total == 13


def test_same_seed_is_repeatable() -> None:
    req = _request(kind="stealth")
    sheet, rider = Sheet(modifiers={"stealth": 2}), Rider()
    a = roll(req, sheet, rider, rng=random.Random(7))
    b = roll(req, sheet, rider, rng=random.Random(7))
    assert (a.natural, a.modifier, a.total) == (b.natural, b.modifier, b.total)
    assert a.modifier == 2


def test_total_integrity_over_a_seed_sweep() -> None:
    sheet = Sheet(modifiers={"athletics": 3})
    for seed in range(50):
        r = roll(_request(kind="athletics"), sheet, Rider(), rng=random.Random(seed))
        assert r.total == r.natural + r.modifier
        assert 1 <= r.natural <= 20
        assert r.modifier == 3


# --- modifier sourcing ---


def test_sheet_only_modifier() -> None:
    sheet = Sheet(modifiers={"perception": 4})
    r = roll(_request(kind="perception"), sheet, Rider(), rng=random.Random(0))
    assert r.modifier == 4
    assert r.total == 17  # 13 + 4


def test_absent_kind_gives_zero_modifier() -> None:
    r = roll(_request(kind="unknown_kind"), Sheet(), Rider(), rng=random.Random(0))
    assert r.modifier == 0
    assert r.total == r.natural


def test_rider_flat_bonus_added_on_kind_match() -> None:
    sheet = Sheet(modifiers={"perception": 1})
    rider = Rider(clauses=[_modify_roll_clause(tags={"perception"}, bonus=2)])
    r = roll(_request(kind="perception"), sheet, rider, rng=random.Random(0))
    assert r.modifier == 3  # sheet 1 + rider 2
    assert r.total == 16  # 13 + 3


def test_rider_non_matching_kind_ignored() -> None:
    rider = Rider(clauses=[_modify_roll_clause(tags={"stealth"}, bonus=5)])
    r = roll(_request(kind="perception"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 0


def test_non_modify_roll_effect_ignored() -> None:
    rider = Rider(
        clauses=[_modify_roll_clause(tags={"perception"}, bonus=5, op=EffectOp.REDUCE)]
    )
    r = roll(_request(kind="perception"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 0


def test_modify_roll_without_bonus_contributes_zero() -> None:
    # An advantage-style payload (no "bonus" key) contributes 0 in v0.
    rider = Rider(clauses=[_modify_roll_clause(tags={"perception"}, bonus=None)])
    r = roll(_request(kind="perception"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 0


def test_empty_tag_clause_is_a_global_bonus() -> None:
    rider = Rider(clauses=[_modify_roll_clause(tags=set(), bonus=1)])
    r = roll(_request(kind="anything"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 1
    assert r.total == 14  # 13 + 1


def test_negative_modifier_validates() -> None:
    sheet = Sheet(modifiers={"strength_save": -1})
    r = roll(_request(kind="strength_save"), sheet, Rider(), rng=random.Random(0))
    assert r.modifier == -1
    assert r.total == 12  # 13 - 1
    assert isinstance(r, RollResult)


# --- contract: correlation + dc ---


def test_correlation_id_is_preserved() -> None:
    req = _request()
    r = roll(req, Sheet(), Rider(), rng=random.Random(0))
    assert r.correlation_id == req.correlation_id


def test_dc_is_ignored() -> None:
    sheet = Sheet(modifiers={"perception": 2})
    with_dc = roll(
        RequestRoll(correlation_id=uuid4(), kind="perception", dc=15),
        sheet,
        Rider(),
        rng=random.Random(3),
    )
    blind = roll(
        RequestRoll(correlation_id=uuid4(), kind="perception", dc=None),
        sheet,
        Rider(),
        rng=random.Random(3),
    )
    assert (with_dc.natural, with_dc.modifier, with_dc.total) == (
        blind.natural,
        blind.modifier,
        blind.total,
    )


# --- model-free (AC5) ---


def test_roll_makes_no_model_call() -> None:
    with recorded_model_calls() as rec:
        roll(_request(), Sheet(), Rider(), rng=random.Random(0))
    assert rec.calls == []


def test_model_call_on_roll_path_is_forbidden() -> None:
    class _Probe(ModelGateway):
        def _invoke(self, request: object) -> object:
            return None

    # The guard is active *inside* roll(); prove it by rolling our own d20 in a
    # rng whose method tries a model call. Simplest: patch a Sheet whose modifier
    # call invokes the gateway. We assert the membrane guard fires from within roll.
    gateway = _Probe()

    class _SneakySheet(Sheet):
        def modifier(self, kind: str) -> int:
            gateway.invoke("roll.sheet.modifier", None)
            return 0

    with pytest.raises(ModelCallForbidden):
        roll(_request(), _SneakySheet(), Rider(), rng=random.Random(0))


# --- public API ---


def test_public_api_is_reexported() -> None:
    import types

    import face_dancer.resolution as resolution

    assert "roll" in resolution.__all__
    assert callable(resolution.roll)
    # the re-export is the function, not the submodule of the same name
    assert not isinstance(resolution.roll, types.ModuleType)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution/test_roll.py -v`
Expected: FAIL — `ImportError: cannot import name 'roll' from 'face_dancer.resolution'` (the module does not exist yet).

- [ ] **Step 3: Write the roll engine module**

Create `src/face_dancer/resolution/roll.py`:

```python
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
```

- [ ] **Step 4: Re-export from the resolution package**

Edit `src/face_dancer/resolution/__init__.py` — KEEP the existing module docstring;
add the `roll` import (the `apply` import sorts before `roll`) and add `"roll"` to
`__all__` (kept sorted):

```python
from face_dancer.resolution.apply import ApplyError, apply
from face_dancer.resolution.roll import roll

__all__ = ["ApplyError", "apply", "roll"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution/test_roll.py -v`
Expected: PASS (16 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/resolution/roll.py src/face_dancer/resolution/__init__.py tests/test_resolution/test_roll.py
git commit -m "feat(resolution): add the model-free roll engine (issue #20)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~187 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
import random
from uuid import uuid4
from face_dancer.protocol import EffectOp, RequestRoll
from face_dancer.resolution import roll
from face_dancer.rider import Rider, Clause, Trigger, RiderEffect
from face_dancer.sheet import Sheet
from face_dancer.membrane import recorded_model_calls
sheet = Sheet(modifiers={'perception': 1})
rider = Rider(clauses=[Clause(claim='keen senses', trigger=Trigger(tags=frozenset({'perception'})),
    kind='mechanical', source='race', effect=RiderEffect(op=EffectOp.MODIFY_ROLL, payload={'bonus': 2}))])
req = RequestRoll(correlation_id=uuid4(), kind='perception', dc=15)
with recorded_model_calls() as rec:
    r = roll(req, sheet, rider, rng=random.Random(0))
print(r.natural, r.modifier, r.total, r.correlation_id == req.correlation_id, rec.calls)
"
# 13 3 16 True []
```

## Out of scope (do NOT implement)

- **Advantage / disadvantage** and contested roll conditions — contested via
  `contest` (per #4); applied later by the resolution loop.
- **Context-conditioned rider modifiers** ("vs poison") needing the originating
  delta's tags — deferred to the resolution loop (#26).
- **Multi-die / damage rolls** — a different message shape.
- The **resolution loop** (#26) that sequences the roll pair into the spine.
- The **real `ModelGateway` adapter** — a brief non-goal.
