# Dynamic State: Schema + Persistence

**Issue:** [#17](https://github.com/GeorgeLautenschlager/face-dancer/issues/17)
**Date:** 2026-06-11
**Status:** Approved

## Purpose

Dynamic state is the volatile, authoritative, **code-written** store: current HP,
conditions, resources, position (brief §3/§5). The character owns and persists
its own state (portability) and it must be non-volatile across sessions. Letting
the model own these numbers is exactly the "silently cheats / heals itself"
failure being removed.

This issue defines the dynamic-state **schema** and its **persistence**. Per the
[#2](https://github.com/GeorgeLautenschlager/face-dancer/issues/2) decision, the
backing store is a JSON blob carried in the character bundle's `state` slot —
there is no separate database. The single authoritative *writer* (the
`apply_delta` executor) and its membrane binding are a **separate issue**; #17
provides the schema state persists as, not the controlled write path.

## Decisions

- **`DynamicState` is a typed pydantic model occupying the bundle's `state`
  slot** — `Bundle.state: dict[str, Any]` becomes `state: DynamicState`. End-to-end
  typing, and the bundle's existing `load`/`unload`/`serialize` round-trip persists
  state directly, so AC3 (non-volatility) falls out of the bundle round-trip with
  no separate persistence layer. The #2 decision explicitly anticipated "the
  `state` slot given a typed model (replacing the opaque dict)." Chosen over a
  standalone model converted to/from an opaque slot, which would cross a manual
  `to_dict`/`from_dict` at every read/write and need AC3 wired by hand.

- **Four fields, all defaulted** — `hp: int = 0`, `conditions: set[str]`,
  `resources: dict[str, int]`, `position: dict[str, Any] | None = None`. All
  default so a fresh character gets a blank state and the bundle can default the
  slot (`Field(default_factory=DynamicState)`). Code authors real values — e.g.
  sets `hp` from the sheet's max HP at creation. `hp` is *current* HP; max HP is
  static and lives on the sheet.

- **`conditions` and `resources` are mutable (`set`/`dict`)** — state is mutated
  in place during play (`state.conditions.add("prone")`, `state.hp = 18`), so
  mutable collections are the ergonomic fit. `conditions` are open strings (the 5e
  names from #3's `CONDITIONS` are guidance, not a constraint — consistent with the
  open-tag decision); `resources` is an open `name → count` map where
  system-specific resources (spell slots, ki, rages) ride without a schema change.

- **`position` is an opaque optional blob** — `dict[str, Any] | None`. Position is
  wholly host-specific (grid `{x,y}`, zone `{zone}`, fleet coords, or `None` for a
  prose game). The character persists it without interpreting it, keeping the
  schema system-agnostic. Chosen over a typed `Position(x,y)` (bakes a grid
  assumption into a system-agnostic protocol) and over omitting it (diverges from
  the brief's named fields and forces a later schema change).

- **`BUNDLE_SCHEMA_VERSION` stays `1`** — no bundle is deployed, and an old
  `"state": {}` still deserializes (every field defaults). Consistent with holding
  the protocol version while the v0 surface is still being assembled.

- **#17 stops at schema + persistence** — state is a mutable, code-written model
  that persists through the bundle. The `apply_delta` executor (the single
  authoritative writer) and the dynamic-state↔membrane binding are deferred to
  their own issue. "No model writes" holds structurally: this module contains no
  LLM call.

## Architecture

A new model in the existing `state` package; one field-type change in the bundle.

```
src/face_dancer/state/
├── __init__.py        # re-exports DynamicState (keeps existing docstring)
└── dynamic_state.py   # NEW: the DynamicState model

src/face_dancer/bundle/
└── container.py       # Bundle.state: dict[str, Any] -> DynamicState
```

Dependency direction: `dynamic_state.py` imports only pydantic + stdlib;
`bundle/container.py` imports `DynamicState` from `face_dancer.state`. Clean
`bundle → state` edge, no cycle.

## The `DynamicState` model (`dynamic_state.py`)

```python
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

## Bundle integration (`container.py`)

```python
from face_dancer.state import DynamicState

class Bundle(BaseModel):
    ...
    state: DynamicState = Field(default_factory=DynamicState)
    ...
```

`Bundle.deserialize` / `load` / `unload` are unchanged — pydantic validates the
nested `state` object on parse and serializes it on dump. A `dict` passed for
`state` is coerced into `DynamicState` (so `Bundle(state={"hp": 18})` still
works), and an old bundle with `"state": {}` loads to a default `DynamicState`.

## Testing

`tests/test_state/test_dynamic_state.py`:

1. **Defaults:** `DynamicState()` has `hp == 0`, empty `conditions`/`resources`,
   `position is None`.
2. **Round-trip:** a populated `DynamicState` (hp, conditions, resources,
   position) satisfies `DynamicState.model_validate(d.model_dump()) == d` and the
   JSON variant.
3. **Mutation:** code can set `hp`, `conditions.add(...)`, `resources[...] = n`,
   and reads return the written values.

Bundle (`tests/test_bundle/test_bundle.py`):

4. **AC3 / DoD:** build a `Bundle`, mutate its `state` in code (set `hp`, add a
   condition, set a resource), `unload` to a tmp path, `load` it back, and assert
   the reloaded bundle's `state` equals the mutated state — load → play → unload →
   reload yields identical state, and a re-read returns the last code-authored
   values.
5. **Update existing fixtures:** the `test_construction_with_values` /
   round-trip tests that pass `state={"hp": 50}` and assert equality against a raw
   dict are updated to the typed `DynamicState` shape (e.g. assert
   `bundle.state == DynamicState(hp=50)` or `bundle.state.hp == 50`).

Re-export check: `face_dancer.state` exposes `DynamicState`. All code passes
`mypy --strict` and the existing ruff config.

## Future consideration (not in scope) — fully opaque state

Worth recording for the sheet/state/perception work ahead: because the **host
owns system knowledge**, it already knows which stats exist and what to propose
deltas against — it never needs to read the character's sheet to know the valid
stat set. That suggests a maximally system-agnostic endpoint where `DynamicState`
is itself *opaque* (the character persists whatever code writes, never
interpreting field names), mirroring the open-tag / opaque-payload / opaque-position
decisions. We are deliberately **not** doing this now: it is large scope creep
that ripples into the sheet schema, perception, and the meaning of "valid," so v0
stays 5e-typed as the guiding light. Flagged here so the typed schema is
understood as a v0 convenience, not a commitment against an opaque store later.

## Out of scope

- The `apply_delta` executor / controlled authoritative write path — its own issue.
- The dynamic-state ↔ membrane (`Proposal`/`dispose`) binding — deferred with the
  executor.
- The sheet and rider schemas — their own issues; those slots stay opaque here.
- SQLite / turn-history backing store — the documented #2 upgrade path, deferred.
- A fully opaque/schemaless `DynamicState` — see "Future consideration" above.
