# apply_delta Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the single code path that applies an authoritative `apply_delta` to `DynamicState`, routed through the membrane `dispose()` so the write is structurally model-free (AC5) and proven (`Applied`).

**Architecture:** `resolution/apply.py` holds `ApplyError`, an op-handler registry (`reduce`, `replace`), and `apply(message, state) -> Applied[DynamicState]`. `apply` wraps the mutation in `dispose(Proposal(delta, origin="session"), disposer)`; the disposer dispatches on the delta's op, mutating `DynamicState` in place via a `target`-addressed payload. Adjudication-only ops and bad payloads raise `ApplyError`.

**Tech Stack:** Python 3.11+, pydantic v2 (consumed models), stdlib, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-apply-delta-executor-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **135 passed**.

---

## Task 1: The executor seam + the `reduce` op

**Files:**
- Create: `src/face_dancer/resolution/apply.py`
- Modify: `src/face_dancer/resolution/__init__.py`
- Test: `tests/test_resolution/__init__.py`, `tests/test_resolution/test_apply.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resolution/__init__.py` as an **empty file** (package marker).

Create `tests/test_resolution/test_apply.py`:

```python
"""Tests for the apply_delta executor — the sole, model-free writer to state."""

from uuid import uuid4

import pytest

from face_dancer.bundle import Bundle
from face_dancer.membrane import Applied, recorded_model_calls
from face_dancer.protocol import ApplyDelta, Delta, EffectOp
from face_dancer.resolution.apply import ApplyError, apply
from face_dancer.state import DynamicState


def _msg(op: EffectOp, payload: dict[str, object]) -> ApplyDelta:
    return ApplyDelta(correlation_id=uuid4(), delta=Delta(op=op, payload=payload))


def test_reduce_hp_mutates_state_with_no_model_call() -> None:
    state = DynamicState(hp=20)
    with recorded_model_calls() as rec:
        result = apply(_msg(EffectOp.REDUCE, {"target": "hp", "amount": 8}), state)
    assert state.hp == 12
    assert rec.calls == []  # AC5: no model on the apply path
    assert isinstance(result, Applied)  # membrane write-proof


def test_reduce_resource_defaults_absent_key_to_zero() -> None:
    state = DynamicState()
    apply(_msg(EffectOp.REDUCE, {"target": "resources", "key": "ki", "amount": 1}), state)
    assert state.resources["ki"] == -1


def test_change_persists_through_a_bundle_round_trip() -> None:
    # AC2: after apply, persisted state reflects the change.
    bundle = Bundle(name="Fighter", state=DynamicState(hp=20))
    apply(_msg(EffectOp.REDUCE, {"target": "hp", "amount": 5}), bundle.state)
    reloaded = Bundle.deserialize(bundle.serialize())
    assert reloaded.state.hp == 15


def test_adjudication_op_is_rejected() -> None:
    state = DynamicState(hp=20)
    with pytest.raises(ApplyError):
        apply(_msg(EffectOp.SCALE, {"target": "hp", "factor": 0.5}), state)


def test_unknown_target_raises() -> None:
    state = DynamicState(hp=20)
    with pytest.raises(ApplyError):
        apply(_msg(EffectOp.REDUCE, {"target": "mana", "amount": 1}), state)


def test_missing_payload_field_raises() -> None:
    state = DynamicState(hp=20)
    with pytest.raises(ApplyError):
        apply(_msg(EffectOp.REDUCE, {"target": "hp"}), state)


def test_public_api_is_reexported() -> None:
    import face_dancer.resolution as resolution

    assert hasattr(resolution, "apply")
    assert hasattr(resolution, "ApplyError")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution/test_apply.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.resolution.apply'`.

- [ ] **Step 3: Write the executor (seam + reduce)**

Create `src/face_dancer/resolution/apply.py`:

```python
"""The apply_delta executor: the single, model-free writer to dynamic state."""

from collections.abc import Callable
from typing import Any

from face_dancer.membrane import Applied, Proposal, dispose
from face_dancer.protocol import ApplyDelta, Delta, EffectOp
from face_dancer.state import DynamicState


class ApplyError(Exception):
    """An apply_delta could not be applied to dynamic state.

    Raised for a non-terminal op (scale/negate/grant_save/modify_roll), an unknown
    payload target, or a payload missing a required field.
    """


def _reduce(state: DynamicState, payload: dict[str, Any]) -> None:
    target = payload["target"]
    amount = payload["amount"]
    if target == "hp":
        state.hp -= amount
    elif target == "resources":
        key = payload["key"]
        state.resources[key] = state.resources.get(key, 0) - amount
    else:
        raise ApplyError(f"reduce: unknown target {target!r}")


_HANDLERS: dict[EffectOp, Callable[[DynamicState, dict[str, Any]], None]] = {
    EffectOp.REDUCE: _reduce,
}


def _apply(delta: Delta, state: DynamicState) -> DynamicState:
    handler = _HANDLERS.get(delta.op)
    if handler is None:
        raise ApplyError(f"{delta.op.value!r} is not a terminal state-write op")
    try:
        handler(state, delta.payload)
    except KeyError as exc:
        raise ApplyError(f"{delta.op.value!r} payload missing field {exc}") from exc
    return state


def apply(message: ApplyDelta, state: DynamicState) -> Applied[DynamicState]:
    """Apply an authoritative apply_delta to dynamic state, model-free.

    The mutation runs inside the membrane's model-free region via ``dispose``;
    the returned ``Applied`` is proof a code-authored write committed.
    """
    proposal: Proposal[Delta] = Proposal(payload=message.delta, origin="session")
    return dispose(proposal, lambda d: _apply(d, state))
```

- [ ] **Step 4: Re-export from the resolution package**

Edit `src/face_dancer/resolution/__init__.py` — KEEP the existing module docstring at the top, and add below it:

```python
from face_dancer.resolution.apply import ApplyError, apply

__all__ = ["ApplyError", "apply"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution/test_apply.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/resolution/apply.py src/face_dancer/resolution/__init__.py tests/test_resolution
git commit -m "feat(resolution): add the model-free apply_delta executor + reduce op (issue #19)"
```

---

## Task 2: The `replace` op

**Files:**
- Modify: `src/face_dancer/resolution/apply.py`
- Test: `tests/test_resolution/test_apply.py`

- [ ] **Step 1: Add the failing replace tests**

Append to `tests/test_resolution/test_apply.py`:

```python
def test_replace_hp_sets_the_value() -> None:
    state = DynamicState(hp=20)
    apply(_msg(EffectOp.REPLACE, {"target": "hp", "value": 7}), state)
    assert state.hp == 7


def test_replace_position_sets_the_blob() -> None:
    state = DynamicState()
    apply(_msg(EffectOp.REPLACE, {"target": "position", "value": {"zone": "bridge"}}), state)
    assert state.position == {"zone": "bridge"}


def test_replace_resource_sets_the_key() -> None:
    state = DynamicState(resources={"ki": 3})
    apply(_msg(EffectOp.REPLACE, {"target": "resources", "key": "ki", "value": 1}), state)
    assert state.resources["ki"] == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution/test_apply.py::test_replace_hp_sets_the_value -v`
Expected: FAIL — `ApplyError: 'replace' is not a terminal state-write op` (REPLACE isn't registered yet).

- [ ] **Step 3: Add the `_replace` handler and register it**

In `src/face_dancer/resolution/apply.py`:

(a) Add `_replace` directly after `_reduce`:

```python
def _replace(state: DynamicState, payload: dict[str, Any]) -> None:
    target = payload["target"]
    value = payload["value"]
    if target == "hp":
        state.hp = value
    elif target == "position":
        state.position = value
    elif target == "resources":
        state.resources[payload["key"]] = value
    else:
        raise ApplyError(f"replace: unknown target {target!r}")
```

(b) Register it in `_HANDLERS`:

```python
_HANDLERS: dict[EffectOp, Callable[[DynamicState, dict[str, Any]], None]] = {
    EffectOp.REDUCE: _reduce,
    EffectOp.REPLACE: _replace,
}
```

- [ ] **Step 4: Run the full resolution suite to verify it passes**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/resolution/apply.py tests/test_resolution/test_apply.py
git commit -m "feat(resolution): add the replace op to the apply executor (issue #19)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~145 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from uuid import uuid4
from face_dancer.protocol import ApplyDelta, Delta, EffectOp
from face_dancer.resolution import apply
from face_dancer.state import DynamicState
from face_dancer.membrane import recorded_model_calls
s = DynamicState(hp=20)
with recorded_model_calls() as rec:
    r = apply(ApplyDelta(correlation_id=uuid4(),
              delta=Delta(op=EffectOp.REDUCE, payload={'target':'hp','amount':8})), s)
print(s.hp, rec.calls, type(r).__name__)
"
# 12 [] Applied
```

## Out of scope (do NOT implement)

- Condition add/remove (set-CRUD); the other effect ops as state writes (scale/negate/grant_save/modify_roll are rejected).
- The rider matcher (#23), the roll engine (#20), the resolution loop (#26), the host/session.
- `propose_delta`/contest handling — apply phase only.
