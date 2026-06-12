# Rules-Rider Artifact Schema

**Issue:** [#18](https://github.com/GeorgeLautenschlager/face-dancer/issues/18)
**Date:** 2026-06-12
**Status:** Approved

## Purpose

Brief §3/§5 — the **rules-rider** carries *reactive*, character-known mechanics a
host can't be assumed to know ("when fire is done to me, here's a rule you may not
know"). The fence: **reactive only** — proactive capability lives in the action
interface (#22), static stats live on the sheet (#16). That bound stops the rider
becoming a second sheet or a rules engine.

This issue defines the rider/clause **schema** and types the bundle's `rider`
slot. The **matcher** — given a `propose_delta`, fire matching clauses into a
`contest`, auto-contesting `mechanical` clauses in code and routing `judgment`
clauses to a mind — belongs to the resolution spine and is **out of scope here**;
#18 carries the data, not the firing logic.

## Decisions

- **Trigger = tags (required) + op (optional wildcard).** `Trigger.tags:
  frozenset[str]` is required; `Trigger.op: EffectOp | None` defaults `None`. A
  clause matches a `propose_delta` when the delta's tags ⊇ the clause's tags AND
  (if the clause sets an op) the ops match; `op=None` matches any op. This lets
  one mechanic ("immune to anything fire") be a single clause (`tags={fire},
  op=None`) — the brief's "spans event shapes without enumerating" goal — while a
  precise clause ("half fire *damage*") sets `op=reduce`. The matcher is a
  set-comparison, defined elsewhere; #18 only represents the trigger.

- **Mandatory `claim` + optional structured `effect` (progressive enhancement).**
  `claim: str` is always present (a prose host reads it; it is the
  progressive-enhancement fallback). `effect: RiderEffect | None` defaults `None`
  — a structured host mechanizes it. A clause with only a `claim` and no `effect`
  is valid (enables AC8).

- **`RiderEffect` is a dedicated `(op, payload)` model.** `op: EffectOp` (closed
  vocabulary only — the rider cannot invent operations, which is what stops it
  becoming a rules engine), `payload: dict[str, Any]`. Chosen over reusing the
  protocol `Delta` model: a reaction has no `tags` of its own the way a `Delta`
  does, so a dedicated lightweight effect is clearer and avoids a meaningless
  field.

- **`kind` is `Literal["mechanical", "judgment"]`.** Mechanical clauses
  auto-contest in code; judgment clauses route one question to a mind. #18 carries
  the tag; the *behavior* is the matcher's.

- **Per-clause `source` provenance (mandatory).** `source: str` records where the
  clause comes from (rulebook page, homebrew ruling). It is what survives
  fine-tuning, which is what makes the rider valuable — so every clause carries it.

- **`order` is an optional proposal.** `order: int | None` defaults `None` — the
  character's declared understanding of resolution sequence, which the session may
  override. Carried, not resolved, here.

- **The fence holds structurally.** A `Clause` *requires* a `trigger`, so it is
  reactive by construction; it has **no field** for a proactive capability (no
  action to invoke) or a static stat (no triggerless value). A field-set
  drift-guard test pins the clause to exactly its six fields, so a capability/stat
  field cannot be added silently. Effects are constrained to the closed
  `EffectOp`. Together these make "a clause cannot encode a proactive capability or
  a static stat" a structural property, not a convention.

- **`Bundle.rider` becomes the typed `Rider`.** `rider: dict[str, Any]` → `rider:
  Rider = Field(default_factory=Rider)`, mirroring how #16/#17 typed sheet/state.
  The bundle round-trip persists it; `BUNDLE_SCHEMA_VERSION` stays `1` (an old
  `"rider": {}` loads to an empty `Rider`).

## Architecture

A new module in the existing `rider/` package; one field-type change in the bundle.

```
src/face_dancer/rider/
├── __init__.py        # re-exports Rider, Clause, Trigger, RiderEffect (keeps docstring)
└── rider.py           # NEW: Trigger, RiderEffect, Clause, Rider

src/face_dancer/bundle/
└── container.py       # Bundle.rider: dict[str, Any] -> Rider
```

Dependency direction: `rider/rider.py` imports `EffectOp` from
`face_dancer.protocol`; `bundle/container.py` imports `Rider` from
`face_dancer.rider`. No cycles.

## The rider schema (`rider/rider.py`)

```python
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

Re-exported from `rider/__init__.py` (keep the existing docstring): `Rider`,
`Clause`, `Trigger`, `RiderEffect`.

## Bundle integration (`container.py`)

```python
from face_dancer.rider import Rider

class Bundle(BaseModel):
    ...
    rider: Rider = Field(default_factory=Rider)
    ...
```

`load`/`unload`/`deserialize` unchanged — pydantic validates the nested `Rider` on
parse. A dict passed for `rider` is coerced; an old `"rider": {}` loads to an
empty `Rider`.

## Testing

`tests/test_rider/test_rider.py`:

1. **Claim-only clause is valid** (AC8): a `Clause` with a `claim`, `trigger`,
   `kind`, `source` and **no `effect`** constructs; `effect is None`.
2. **Trigger required (fence / reactive-by-construction):** a clause built without
   a `trigger` raises `ValidationError`.
3. **Trigger op optional, tags required:** `Trigger(tags=frozenset({"fire"})).op
   is None`; `Trigger()` (no tags) raises `ValidationError`.
4. **Effect op is closed:** a `RiderEffect` / clause-effect with an op outside
   `EffectOp` (e.g. `"teleport"`) raises `ValidationError`; a valid op parses to
   the enum.
5. **Clause field-set guard (the fence):** `set(Clause.model_fields) == {"claim",
   "trigger", "kind", "source", "effect", "order"}` — no capability/stat field can
   be added silently.
6. **Round-trip:** a fully-populated `Rider` (a mechanical clause with an effect +
   a judgment claim-only clause) round-trips python + JSON (`==`).
7. **Rider defaults:** `Rider()` has `clauses == []`.
8. **Public API:** `face_dancer.rider` re-exports `Rider`, `Clause`, `Trigger`,
   `RiderEffect`.

`tests/test_bundle/test_bundle.py`:

9. **Bundle round-trip with a populated rider** survives `unload → load` (`==`).
10. **Update existing fixtures** that pass `rider={...}` and assert against a raw
    dict to the typed `Rider` shape.

`tests/test_rider/__init__.py` empty package marker. All code passes
`mypy --strict` and the existing ruff config.

## Out of scope

- The **matcher** — firing clauses on a `propose_delta`, the op+tag-set comparison,
  emitting a `contest`: the resolution-spine issue.
- **`mechanical` vs `judgment` behavior** (auto-contest vs route to a mind) — the
  matcher's; #18 only carries the tag.
- **`order` resolution** — carried as a proposal; sequencing is the resolver's.
- Perception, the decision policy, the roll engine.
- A `BUNDLE_SCHEMA_VERSION` bump.
