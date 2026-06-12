# Rules-Rider Artifact Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the rider/clause schema (`Trigger`, `RiderEffect`, `Clause`, `Rider`) and type the bundle's `rider` slot with it. The matcher is out of scope.

**Architecture:** A new `rider/rider.py` holds four pydantic models. A clause is reactive by construction (it requires a `trigger`), carries a mandatory `claim` + optional structured `effect` (closed `EffectOp` only), a `mechanical`/`judgment` kind, `source` provenance, and an optional `order`. The bundle's `rider` field changes from `dict[str, Any]` to `Rider`. `BUNDLE_SCHEMA_VERSION` stays 1.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-12-rules-rider-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **109 passed**.

---

## Task 1: The rider schema (`rider/rider.py`)

**Files:**
- Create: `src/face_dancer/rider/rider.py`
- Modify: `src/face_dancer/rider/__init__.py`
- Test: `tests/test_rider/__init__.py`, `tests/test_rider/test_rider.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rider/__init__.py` as an **empty file** (package marker).

Create `tests/test_rider/test_rider.py`:

```python
"""Tests for the rules-rider schema: clauses, triggers, and the reactive fence."""

import pytest
from pydantic import ValidationError

from face_dancer.protocol import EffectOp
from face_dancer.rider.rider import Clause, Rider, RiderEffect, Trigger


def test_claim_only_clause_is_valid() -> None:
    c = Clause(
        claim="I have fire resistance",
        trigger=Trigger(tags=frozenset({"fire"})),
        kind="mechanical",
        source="PHB p.1",
    )
    assert c.effect is None
    assert c.order is None


def test_trigger_is_required() -> None:
    with pytest.raises(ValidationError):
        Clause(claim="x", kind="mechanical", source="x")


def test_trigger_op_optional_tags_required() -> None:
    assert Trigger(tags=frozenset({"fire"})).op is None
    with pytest.raises(ValidationError):
        Trigger()


def test_effect_op_is_closed() -> None:
    e = RiderEffect.model_validate({"op": "scale", "payload": {"factor": 0.5}})
    assert e.op is EffectOp.SCALE
    with pytest.raises(ValidationError):
        RiderEffect.model_validate({"op": "teleport"})


def test_clause_field_set_is_the_fence() -> None:
    # Reactive only: no capability/stat field can be added silently.
    assert set(Clause.model_fields) == {
        "claim",
        "trigger",
        "kind",
        "source",
        "effect",
        "order",
    }


def test_rider_round_trips() -> None:
    rider = Rider(
        clauses=[
            Clause(
                claim="Half damage from fire",
                trigger=Trigger(tags=frozenset({"fire"}), op=EffectOp.REDUCE),
                kind="mechanical",
                source="race: tiefling",
                effect=RiderEffect(op=EffectOp.SCALE, payload={"factor": 0.5}),
                order=1,
            ),
            Clause(
                claim="I argue I should get a save vs this",
                trigger=Trigger(tags=frozenset({"charm"})),
                kind="judgment",
                source="homebrew",
            ),
        ]
    )
    assert Rider.model_validate(rider.model_dump()) == rider
    assert Rider.model_validate_json(rider.model_dump_json()) == rider


def test_rider_defaults_empty() -> None:
    assert Rider().clauses == []


def test_public_api_is_reexported() -> None:
    import face_dancer.rider as rider

    for name in ("Rider", "Clause", "Trigger", "RiderEffect"):
        assert hasattr(rider, name)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_rider -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.rider.rider'`.

- [ ] **Step 3: Write the schema module**

Create `src/face_dancer/rider/rider.py`:

```python
"""The rules-rider schema: reactive, character-known clauses the host may not know."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from face_dancer.protocol import EffectOp


class Trigger(BaseModel):
    """What a clause reacts to: a required tag-set and an optional op wildcard.

    A clause matches a propose_delta when the delta's tags are a superset of
    ``tags`` and, if ``op`` is set, the delta's op equals it. ``op=None`` matches
    any op (one mechanic spanning damage/conditions/saves without enumerating).
    """

    tags: frozenset[str]
    op: EffectOp | None = None


class RiderEffect(BaseModel):
    """A structured reaction the character proposes — drawn from the closed op set.

    Progressive enhancement over ``claim``: a structured host mechanizes this; the
    closed ``EffectOp`` keeps the rider from becoming a rules engine.
    """

    op: EffectOp
    payload: dict[str, Any] = Field(default_factory=dict)


class Clause(BaseModel):
    """One reactive, character-known rule the host may not know.

    Reactive by construction (it requires a ``trigger``); it can encode neither a
    proactive capability nor a static stat — that fence is what keeps the rider
    from becoming a second sheet.
    """

    claim: str
    trigger: Trigger
    kind: Literal["mechanical", "judgment"]
    source: str
    effect: RiderEffect | None = None
    order: int | None = None


class Rider(BaseModel):
    """The character's reactive rules: an ordered set of clauses."""

    clauses: list[Clause] = Field(default_factory=list)
```

- [ ] **Step 4: Re-export from the package**

Edit `src/face_dancer/rider/__init__.py` — KEEP the existing module docstring at the top, and add below it:

```python
from face_dancer.rider.rider import Clause, Rider, RiderEffect, Trigger

__all__ = ["Clause", "Rider", "RiderEffect", "Trigger"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_rider -v`
Expected: PASS (8 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/rider/rider.py src/face_dancer/rider/__init__.py tests/test_rider
git commit -m "feat(rider): add rules-rider clause schema (issue #18)"
```

---

## Task 2: Type the bundle's `rider` slot

**Files:**
- Modify: `src/face_dancer/bundle/container.py`
- Modify: `tests/test_bundle/test_bundle.py`

- [ ] **Step 1: Change the bundle's `rider` field to the typed `Rider`**

In `src/face_dancer/bundle/container.py`:

(a) Add the import — it sorts among the `face_dancer.*` imports (`bundle.errors`,
`bundle.version`, `rider`, `sheet`, `state`); place it after the bundle imports
and before `sheet`:

```python
from face_dancer.bundle.errors import BundleError, BundleVersionError
from face_dancer.bundle.version import BUNDLE_SCHEMA_VERSION
from face_dancer.rider import Rider
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState
```

(b) Change the `rider` field:

```python
    rider: Rider = Field(default_factory=Rider)
```

(c) **Remove the now-unused `Any` import.** `rider: dict[str, Any]` was the only
remaining use of `Any` in this file (sheet/state are already typed), so after this
change `from typing import Any` (line 3) is unused and ruff (`F401`) will fail.
Delete that import line entirely.

- [ ] **Step 2: Update the existing bundle fixtures for the typed rider**

In `tests/test_bundle/test_bundle.py`:

(a) Add the import below the existing `from face_dancer.sheet import Sheet` import:

```python
from face_dancer.rider import Clause, Rider, Trigger
```

(b) In `test_construction`, change the empty-rider assertion:

```python
    assert bundle.rider == Rider()
```

(c) In `test_construction_with_values`, replace the `rider = {"rules": "no dice"}`
line and its assertion. Build a real `Rider` and assert it survives:

```python
    rider = Rider(
        clauses=[
            Clause(
                claim="I resist fire",
                trigger=Trigger(tags=frozenset({"fire"})),
                kind="mechanical",
                source="homebrew",
            )
        ]
    )
```
and (the assertion line stays `assert bundle.rider == rider`, now comparing
`Rider`s):

```python
    assert bundle.rider == rider
```

(d) In `test_round_trip_populated`, replace the `rider={"rule": 3}` line with a
valid rider dict (the bare `{"rule": 3}` would be dropped as an unknown key), so
the populated round-trip exercises dict→`Rider` coercion:

```python
        rider={
            "clauses": [
                {
                    "claim": "x",
                    "trigger": {"tags": ["fire"]},
                    "kind": "mechanical",
                    "source": "phb",
                }
            ]
        },
```

- [ ] **Step 3: Run the bundle suite (and full suite)**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_bundle -v`
Expected: PASS. (`test_round_trip_populated` now round-trips a populated `Rider`,
covering bundle-with-rider persistence.)

- [ ] **Step 4: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 5: Commit**

```bash
git add src/face_dancer/bundle/container.py tests/test_bundle/test_bundle.py
git commit -m "feat(bundle): persist typed Rider in the rider slot (issue #18)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~117 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from face_dancer.rider import Rider, Clause, Trigger, RiderEffect
from face_dancer.protocol import EffectOp
from face_dancer.bundle import Bundle
r = Rider(clauses=[Clause(claim='resist fire',
    trigger=Trigger(tags=frozenset({'fire'})), kind='mechanical', source='race',
    effect=RiderEffect(op=EffectOp.SCALE, payload={'factor': 0.5}))])
b = Bundle(name='Tiefling', rider=r)
print(Bundle.deserialize(b.serialize()).rider == r)
print(Rider().clauses)
"
# True
# []
```

## Out of scope (do NOT implement)

- The matcher — firing clauses on a propose_delta, the op+tag-set comparison, the contest.
- `mechanical` vs `judgment` behavior; `order` resolution.
- Perception, decision policy, roll engine.
- A `BUNDLE_SCHEMA_VERSION` bump.
