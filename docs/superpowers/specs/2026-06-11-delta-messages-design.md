# Delta Messages: `propose_delta` + `apply_delta`

**Issue:** [#11](https://github.com/GeorgeLautenschlager/face-dancer/issues/11)
**Date:** 2026-06-11
**Status:** Approved

## Purpose

Two-phase propose/apply is the load-bearing spine of the protocol (brief §3/§5):
a delta is *proposed* before it commits, so the character can `contest` before
the write. This cannot be retrofitted onto a single-shot apply.

Issue #9 stood up `propose_delta` and `apply_delta` as thin placeholders
(`target` + `tags` + `effects: list[dict]`) so the message union existed. This
issue replaces those placeholders with the real, shared **delta shape** —
`(op, tags, payload)` — built on the closed `EffectOp` vocabulary from
[#3](https://github.com/GeorgeLautenschlager/face-dancer/issues/3), and makes
"proposed vs. authoritative" unambiguous in the schema.

Deliverables:

1. A first-class `Delta` model — one `op`, a tag-set, an open `payload`.
2. `propose_delta` and `apply_delta` rebodied to carry a `Delta`, sharing the
   one model so the two carry identical structure.
3. A regenerated published JSON Schema reflecting the real shape.

## Decisions

- **One delta = one effect** — a `Delta` carries exactly one `op` + tag-set +
  payload, matching the issue's singular `(op, tags, payload)` and the brief's
  "a delta carries an op plus a tag-set." A game event with several effects
  (damage *and* a condition) is several deltas, each independently
  proposed/contested/applied. Chosen over a `delta.effects: list[Effect]` shape:
  per-delta atomicity keeps `contest` unambiguous (you contest *a* delta, not
  "which effect in the list") and lets the rider match one `op` + tag-set without
  scanning a list.

- **First-class `Delta` model, composed (not inherited)** — `Delta(op, tags,
  payload)` is its own model; both messages carry `delta: Delta`. This makes the
  shared shape a real, reusable object the rider matcher, the apply executor, and
  the membrane seam (`Proposal[Delta]` / `Applied`) operate on independently of
  the wire envelope. Chosen over a shared `_DeltaMessage(Envelope)` base class:
  inheritance would flatten the fields onto the message but leave no standalone
  delta object to hand to those downstream consumers.

- **`payload` is an open `dict[str, Any]`** — the per-op payload schemas (what
  `reduce` carries vs. `grant_save`) belong to the executor/resolution issue that
  owns applying them. #11 owns the shared *shape*, not per-op internals — the
  same thin-body discipline #9 used for `effects`. The protocol carries the
  payload without asserting its per-op structure.

- **`op` is the closed `EffectOp` enum** — a delta's operation is validated
  against the closed, versioned vocabulary from #3. An unknown op is a structural
  validation failure (a `ProtocolError` out of `validate()`), not an open string.

- **No `target` field** — a delta is applied by the character to *its own*
  dynamic state; the session sends each character its own delta, so the target is
  implicit. Per-resource targeting, if ever needed, rides in `payload`; it is not
  part of the v0 shape. (Drops the #9 placeholder's `target: str`.)

- **Proposed vs. authoritative is the `type` discriminator alone** — the union
  already dispatches `propose_delta` → `ProposeDelta` and `apply_delta` →
  `ApplyDelta`, so the distinction is unambiguous in the schema. No redundant
  `authoritative: bool` flag — that would encode the same fact twice and could
  contradict the `type`. `apply_delta` shares its `correlation_id` with the
  `propose_delta` it finalizes (existing envelope semantics, unchanged).

- **`SCHEMA_VERSION` stays `1`** — this changes the wire shape of two messages,
  but no host has implemented v1 yet: the published schema is an in-repo artifact
  only, and #11 is part of *assembling* the v1 surface, not altering a contract a
  deployed host already speaks. We bump when we first deploy. The committed
  `docs/protocol/schema.json` is regenerated so the published shape matches.

## Architecture

A new leaf module under the protocol package; the message bodies change to
compose it.

```
src/face_dancer/protocol/
├── delta.py        # NEW: the Delta model (op, tags, payload)
├── messages.py     # ProposeDelta/ApplyDelta now carry `delta: Delta`
├── vocabulary.py   # EffectOp (from #3) — Delta imports it
├── __init__.py     # re-exports Delta
└── ...
```

Dependency direction: `delta.py` imports `vocabulary.py` (for `EffectOp`) and
nothing else in the package; `messages.py` imports `delta.py` and `envelope.py`.
No cycles. The `Message` union and `MESSAGE_TYPES` registry in `messages.py` are
unchanged — same two `type` tags, new bodies.

## The `Delta` model (`delta.py`)

```python
from typing import Any

from pydantic import BaseModel, Field

from face_dancer.protocol.vocabulary import EffectOp


class Delta(BaseModel):
    """One effect: a single op, the tag-set it applies under, and its payload.

    The op is drawn from the closed EffectOp vocabulary. `tags` is open
    (frozenset[str]) — the rider matches on op + tag-set. `payload` is an open
    dict; the per-op payload schemas belong to the executor that applies them.
    """

    op: EffectOp
    tags: frozenset[str] = frozenset()
    payload: dict[str, Any] = Field(default_factory=dict)
```

## The messages (`messages.py`)

`ProposeDelta` and `ApplyDelta` lose `target`/`tags`/`effects` and gain
`delta: Delta`:

```python
from face_dancer.protocol.delta import Delta


class ProposeDelta(Envelope):
    """Session-proposed change, not yet committed (session -> character)."""

    type: Literal["propose_delta"] = "propose_delta"
    delta: Delta


class ApplyDelta(Envelope):
    """Authoritative change the character's code applies (session -> character).

    Shares ``correlation_id`` with the ``propose_delta`` it finalizes.
    """

    type: Literal["apply_delta"] = "apply_delta"
    delta: Delta
```

The other four message types, the `Message` union, and `MESSAGE_TYPES` are
untouched.

## Public API (`__init__.py`)

Re-export `Delta` alongside the existing names, added to `__all__` (kept sorted):

```python
from face_dancer.protocol.delta import Delta
```

## Published schema (`docs/protocol/schema.json`)

The committed JSON Schema is regenerated after the body change:

```bash
PYTHONPATH="$PWD/src" python3 -m face_dancer.protocol.validation
```

The existing drift guard (`test_committed_schema_matches_export`) enforces that
the committed artifact equals a fresh `export_schema()`, so regeneration is
mandatory, not optional.

## Testing

Extend `tests/test_protocol/`:

1. **Delta round-trip through both messages:** a `ProposeDelta` and an
   `ApplyDelta` carrying a populated `Delta` (a real `EffectOp`, tags, payload)
   round-trip `validate(m.model_dump()) == m` and
   `validate(m.model_dump_json()) == m`.
2. **`op` validates against `EffectOp`:** a raw message whose `delta.op` is not a
   known op raises a `ProtocolError` from `validate()`; a valid op parses to the
   `EffectOp` member.
3. **Defaults:** a `Delta` built with only `op` has `tags == frozenset()` and
   `payload == {}`.
4. **Dispatch unchanged:** `validate()` still maps `propose_delta` →
   `ProposeDelta` and `apply_delta` → `ApplyDelta`, each carrying a `Delta`.
5. **Schema:** regenerate `docs/protocol/schema.json`; the three `test_schema.py`
   assertions (six-member tagged union, discriminator mapping, committed ==
   export) pass.
6. **Update existing fixtures** that build the old shape to the new `delta=`
   form: `tests/test_protocol/test_messages.py` (the `_one_of_each` ProposeDelta
   / ApplyDelta) and `tests/test_protocol/test_validation.py` (lines constructing
   `ProposeDelta(..., target=...)` / `ApplyDelta(..., target=...)`).
7. Re-export check: `face_dancer.protocol` exposes `Delta`.

All code passes `mypy --strict` and the existing ruff config.

## Out of scope

- **Per-op payload schemas** (the shape of `reduce`'s payload vs. `grant_save`'s)
  — the executor/resolution issue that applies them.
- **The rider matcher** (op + tag-set comparison) — the rider issue; it consumes
  `Delta` and the #3 tag constants.
- **The apply executor** (code that writes an `apply_delta` into dynamic state) —
  its own issue.
- **`contest` / `request_roll` / `roll_result` changes** — untouched here.
- **A `SCHEMA_VERSION` bump** — deferred to first deployment.
