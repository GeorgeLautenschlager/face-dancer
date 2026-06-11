# Dynamic State (schema + persistence) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give dynamic state a typed `DynamicState` model and persist it through the bundle's `state` slot (replacing the opaque `dict`), so `load → play → unload → reload` yields identical state (AC3).

**Architecture:** A new `DynamicState` pydantic model in the `state` package (current HP, conditions, resources, opaque position); the bundle's `state` field changes from `dict[str, Any]` to `DynamicState`, so the bundle's existing load/unload round-trip persists state. No separate persistence layer (the #2 JSON-blob decision). The authoritative write path / `apply_delta` executor is a separate, later issue.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-11-dynamic-state-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **72 passed**.

---

## Task 1: The `DynamicState` model

**Files:**
- Create: `src/face_dancer/state/dynamic_state.py`
- Modify: `src/face_dancer/state/__init__.py`
- Test: `tests/test_state/__init__.py`, `tests/test_state/test_dynamic_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state/__init__.py` as an **empty file** (package marker, like `tests/test_protocol/__init__.py`).

Create `tests/test_state/test_dynamic_state.py`:

```python
"""Tests for the DynamicState model — the volatile, code-written state store."""

from face_dancer.state.dynamic_state import DynamicState


def test_defaults_are_blank() -> None:
    s = DynamicState()
    assert s.hp == 0
    assert s.conditions == set()
    assert s.resources == {}
    assert s.position is None


def test_round_trips_through_python_and_json() -> None:
    s = DynamicState(
        hp=18,
        conditions={"prone", "poisoned"},
        resources={"spell_slot_1": 3, "ki": 2},
        position={"x": 3, "y": 7},
    )
    assert DynamicState.model_validate(s.model_dump()) == s
    assert DynamicState.model_validate_json(s.model_dump_json()) == s


def test_code_mutates_in_place() -> None:
    s = DynamicState(hp=20)
    s.hp = 12
    s.conditions.add("prone")
    s.resources["ki"] = 1
    s.position = {"zone": "bridge"}
    assert s.hp == 12
    assert "prone" in s.conditions
    assert s.resources["ki"] == 1
    assert s.position == {"zone": "bridge"}


def test_public_api_is_reexported() -> None:
    import face_dancer.state as state

    assert hasattr(state, "DynamicState")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_state -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.state.dynamic_state'`.

- [ ] **Step 3: Write the model**

Create `src/face_dancer/state/dynamic_state.py`:

```python
"""The DynamicState model: the character's volatile, code-written state."""

from typing import Any

from pydantic import BaseModel, Field


class DynamicState(BaseModel):
    """The character's volatile, authoritative, code-written state.

    Current HP, active conditions, consumable resources, and an opaque
    host-defined position. Every field is mutated only by code; the model never
    writes here. Max HP and static stats live on the sheet, not here.
    """

    hp: int = 0
    conditions: set[str] = Field(default_factory=set)
    resources: dict[str, int] = Field(default_factory=dict)
    position: dict[str, Any] | None = None
```

- [ ] **Step 4: Re-export from the package**

Edit `src/face_dancer/state/__init__.py` — KEEP the existing module docstring at the top, and add below it:

```python
from face_dancer.state.dynamic_state import DynamicState

__all__ = ["DynamicState"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_state -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/state/dynamic_state.py src/face_dancer/state/__init__.py tests/test_state
git commit -m "feat(state): add the DynamicState model (issue #17)"
```

---

## Task 2: Wire `DynamicState` into the bundle + AC3 persistence

**Files:**
- Modify: `src/face_dancer/bundle/container.py`
- Modify: `tests/test_bundle/test_bundle.py`

- [ ] **Step 1: Change the bundle's `state` field to the typed model**

In `src/face_dancer/bundle/container.py`:

(a) Add the import — it sorts **after** the two `face_dancer.bundle.*` imports (`bundle` < `state`):

```python
from face_dancer.bundle.errors import BundleError, BundleVersionError
from face_dancer.bundle.version import BUNDLE_SCHEMA_VERSION
from face_dancer.state import DynamicState
```

(b) Change the `state` field (leave `sheet` and `rider` as `dict[str, Any]`, so the `Any` import stays):

```python
    state: DynamicState = Field(default_factory=DynamicState)
```

- [ ] **Step 2: Update the existing bundle fixtures for the typed state**

In `tests/test_bundle/test_bundle.py`:

(a) Add the import below the existing `from face_dancer.bundle.*` imports:

```python
from face_dancer.state import DynamicState
```

(b) In `test_construction`, change the empty-state assertion:

```python
    assert bundle.state == DynamicState()
```
(leave `assert bundle.sheet == {}` and `assert bundle.rider == {}` unchanged).

(c) In `test_construction_with_values`, the `state = {"hp": 50}` dict is coerced
into a `DynamicState`, so the equality assertion must compare against the typed
model. Change ONLY the state assertion line to:

```python
    assert bundle.state == DynamicState(hp=50)
```
(`sheet` and `rider` remain dicts; leave their assertions unchanged.)

(d) In `test_round_trip_populated`, replace the `state={"val": 2}` line (the `val`
key is not a `DynamicState` field and would be silently dropped) with a real
field so the populated round-trip is meaningful:

```python
        state={"hp": 7, "conditions": ["prone"]},
```

- [ ] **Step 3: Add the AC3 / DoD persistence test**

Append to `tests/test_bundle/test_bundle.py`:

```python
def test_state_survives_load_play_unload_reload(tmp_path: Path) -> None:
    # AC3: load -> play (code mutates state) -> unload -> reload yields identical state.
    bundle = Bundle(name="Fighter")
    bundle.state.hp = 18
    bundle.state.conditions.add("prone")
    bundle.state.resources["second_wind"] = 1

    path = tmp_path / "char.json"
    bundle.unload(path)
    reloaded = Bundle.load(path)

    assert reloaded.state == bundle.state
    assert reloaded.state.hp == 18
    assert "prone" in reloaded.state.conditions
    assert reloaded.state.resources["second_wind"] == 1
```

- [ ] **Step 4: Run the full suite**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest -q`
Expected: PASS — **77 passed** (72 baseline + 4 DynamicState + 1 AC3 bundle test; the edited fixtures are modified, not added).

- [ ] **Step 5: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/bundle/container.py tests/test_bundle/test_bundle.py
git commit -m "feat(bundle): persist typed DynamicState in the state slot (issue #17)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # 77 passed
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from pathlib import Path; import tempfile
from face_dancer.bundle import Bundle
from face_dancer.state import DynamicState
b = Bundle(name='X'); b.state.hp = 24; b.state.conditions.add('prone')
p = Path(tempfile.mkdtemp()) / 'c.json'; b.unload(p)
r = Bundle.load(p)
print(r.state == b.state, r.state.hp, sorted(r.state.conditions))
"
# True 24 ['prone']
```

## Out of scope (do NOT implement)

- The `apply_delta` executor / controlled authoritative write path — its own issue.
- The dynamic-state ↔ membrane (`Proposal`/`dispose`) binding.
- The sheet and rider schemas (their slots stay `dict[str, Any]`).
- SQLite / turn-history; a fully opaque/schemaless DynamicState (see spec's "Future consideration").
- A `BUNDLE_SCHEMA_VERSION` bump.
