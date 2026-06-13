# apply_delta Executor — The Sole Writer to Dynamic State

**Issue:** [#19](https://github.com/GeorgeLautenschlager/face-dancer/issues/19)
**Date:** 2026-06-13
**Status:** Approved

## Purpose

Brief §5 — **code authors all writes; the LLM never mutates state or does
arithmetic.** This executor is the single code path that applies an authoritative
`apply_delta` to dynamic state. Centralizing it is what guarantees the model is
never on the write path.

Issue #11 deliberately deferred the per-op payload schemas ("what `reduce` carries
vs. `grant_save`") to *the executor that applies them* — this issue. So #19 owns
both the write path *and* the v0 mapping from a delta's `(op, payload)` onto the
`DynamicState` fields (`hp`, `conditions`, `resources`, `position`).

## Decisions

- **The write runs through the membrane `dispose()`.** `apply()` wraps the
  mutation in `dispose(Proposal(delta, origin="session"), disposer)`, which runs
  the disposer inside a `model_calls_forbidden` region and mints an
  `Applied[DynamicState]` proof. So **no model call can occur on the apply path
  (AC5) structurally**, and a committed write is provable — the executor *is* a
  disposer, the same seam #24's tactical path uses.

- **`apply()` returns `Applied[DynamicState]`.** It surfaces the membrane's
  write-proof rather than a bare state. The `DynamicState` is mutated **in place**
  (it is mutable by design, #17); persistence is the bundle's job (`state` is
  `bundle.state`), so AC2 = *the executor mutates, the bundle round-trip persists*.

- **An extensible op-handler registry; v0 handles `reduce` and `replace`.** A
  `{EffectOp: handler}` table. Each handler reads a `target`-addressed payload:
  - `reduce` — numeric decrement: `payload{target, amount, [key]}`. `target="hp"`
    → `state.hp -= amount`; `target="resources"` → `state.resources[key] -=
    amount` (defaulting an absent key to 0).
  - `replace` — set a field: `payload{target, value, [key]}`. `target="hp"` →
    `state.hp = value`; `target="position"` → `state.position = value`;
    `target="resources"` → `state.resources[key] = value`.
  More ops drop into the registry later without touching the seam.

- **The adjudication-only ops raise.** `scale`, `negate`, `grant_save`,
  `modify_roll` are resolved by the session *before* it sends an authoritative
  `apply_delta` (resistance halves the damage; the apply carries the final
  `reduce`). They are not terminal state writes, so reaching the executor is an
  error → `ApplyError`. An **unknown `target`** or a **missing payload field**
  (`amount`/`value`/`key`) likewise raises `ApplyError`.

- **Condition add/remove is deferred.** The closed effect-op vocabulary doesn't
  cleanly express set-CRUD on `conditions`; that mapping lands with the
  resolution/rider work that needs it. `conditions` remains writable by code, just
  not via this v0 op set.

- **Sole writer.** This `apply()` is the single delta→state path; "no *other* code
  writes state" is architectural (`DynamicState` is deliberately mutable for code),
  while "no *model* on the write path" is structural via `dispose`.

## Architecture

A new module in the existing `resolution/` package.

```
src/face_dancer/resolution/
├── __init__.py     # re-exports apply, ApplyError (keeps the docstring)
└── apply.py        # NEW: apply(), ApplyError, the op-handler registry
```

Dependency direction: `apply.py` imports `ApplyDelta`/`Delta`/`EffectOp`
(`face_dancer.protocol`), `DynamicState` (`face_dancer.state`), and
`Proposal`/`Applied`/`dispose` (`face_dancer.membrane`). No cycles.

## The executor (`resolution/apply.py`)

```python
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


_HANDLERS: dict[EffectOp, Callable[[DynamicState, dict[str, Any]], None]] = {
    EffectOp.REDUCE: _reduce,
    EffectOp.REPLACE: _replace,
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

Re-exported from `resolution/__init__.py` (keep the docstring): `apply`,
`ApplyError`.

## Testing

`tests/test_resolution/test_apply.py`:

1. **AC2 + AC5 — reduce hp (the fire-damage case):** within `recorded_model_calls()`,
   `apply(ApplyDelta(... Delta(op=REDUCE, payload={"target": "hp", "amount": 8})),
   state)` leaves `state.hp` decreased by 8, the recorder is **empty** (no model
   call), and the return is an `Applied`.
2. **AC2 persistence:** apply a `reduce` to `bundle.state`, `Bundle.deserialize(
   bundle.serialize())`, and the change survives the round-trip.
3. **reduce a resource:** `payload={"target": "resources", "key": "ki", "amount":
   1}` decrements `state.resources["ki"]` (absent key defaults to 0 → −1).
4. **replace hp / position / resource:** each sets the field to `value`.
5. **A modifier op raises:** `Delta(op=SCALE, ...)` → `ApplyError`.
6. **Unknown target raises:** `reduce` with `target="mana"` → `ApplyError`.
7. **Missing payload field raises:** `reduce` with no `amount` → `ApplyError`.
8. **Public API:** `face_dancer.resolution` re-exports `apply`, `ApplyError`.

`tests/test_resolution/__init__.py` empty package marker. All code passes
`mypy --strict` and the existing ruff config.

## Out of scope

- **Condition add/remove** (set-CRUD) — deferred to the resolution/rider work.
- **The other effect ops** as state writes — scale/negate/grant_save/modify_roll
  are adjudication-time, resolved before apply (this executor rejects them).
- **The rider matcher** (#23), the **roll engine** (#20), the **resolution loop**
  (#26) that calls this executor, and the **host/session** that sends the
  authoritative `apply_delta`.
- **`propose_delta` handling / contest** — this is the apply phase only.
