# contest Message — Claims, Not Verdicts

**Issue:** [#12](https://github.com/GeorgeLautenschlager/face-dancer/issues/12)
**Date:** 2026-06-13
**Status:** Approved

## Purpose

Brief §5 — `contest` carries **claims, not verdicts**. The character surfaces
rules it knows ("I have fire resistance and a save"); the session still
adjudicates and owns the final number. This is shared interpretation *without*
ceding authority — the one recourse the character has against a proposed delta.

Issue #9 stood `contest` up as a thin placeholder (`claims: list[str]`). This
issue gives it the real schema: a list of **claims**, each ≈ a matched rider
clause (a mandatory prose `claim` + an optional structured `effect`), with a
**verdict made structurally unrepresentable**.

## Decisions

- **A claim is `claim` (prose) + an optional structured `effect`.** Each `Claim`
  mirrors a matched rider clause: a mandatory `claim: str` (the prose a dumb host
  reads) and an optional `effect` a structured host mechanizes — progressive
  enhancement, same as the rider's clause/effect split (#18). A claim-only `Claim`
  is valid (the prose fallback).

- **The structured effect is a dedicated protocol `ClaimEffect(op, payload)`.** It
  mirrors the rider's `RiderEffect` shape exactly — `op` from the closed
  `EffectOp` vocabulary plus an open `payload`, **no tags** (it's a reaction
  suggestion, not a tagged event, per the #18 decision). It cannot *be*
  `RiderEffect`: the contest is a protocol message, and `protocol` must not depend
  on `rider` (that's the wrong dependency direction). So `ClaimEffect` is the
  protocol-level twin; the rider matcher (#23) maps a clause's `RiderEffect` →
  `ClaimEffect` trivially. Chosen over reusing `Delta`, which would drag in a
  meaningless `tags` field.

- **A verdict is structurally unrepresentable (the DoD).** A claim carries a prose
  claim + an optional `op`+`payload` *suggestion*; there is **no result / total /
  verdict field** anywhere. The effect is the character's *proposed* modification
  (a claim the session adjudicates), never the final number. A **field-set
  drift-guard** pins `Claim` to exactly `{claim, effect}` and `ClaimEffect` to
  `{op, payload}`, so a `result`/`total` field cannot be added silently — "a
  contest can never assert 'therefore 14'" is a property of the schema, not a
  convention. (No explicit "this is not a verdict" marker; the absence is the
  guarantee.)

- **`SCHEMA_VERSION` stays `1`; regenerate `docs/protocol/schema.json`.** The
  `Contest` body changes shape, but no host implements v1 yet (we're still
  assembling the v0 surface); the published schema is regenerated and the drift
  guard enforces it.

## Architecture

A new leaf module under the protocol package; `Contest`'s body changes to compose
it.

```
src/face_dancer/protocol/
├── contest.py      # NEW: ClaimEffect, Claim
├── messages.py     # Contest now carries `claims: list[Claim]`
├── __init__.py     # re-exports Claim, ClaimEffect
└── ...
```

Dependency direction: `contest.py` imports `EffectOp` from
`face_dancer.protocol.vocabulary`; `messages.py` imports `Claim` from
`contest.py`. No cycles (parallels how `delta.py` is composed into `messages.py`).
The `Message` union and the other five message types are unchanged.

## The claim schema (`protocol/contest.py`)

```python
from typing import Any

from pydantic import BaseModel, Field

from face_dancer.protocol.vocabulary import EffectOp


class ClaimEffect(BaseModel):
    """A structured suggestion a claim may carry — an op + payload, never a verdict.

    Mirrors the rider's RiderEffect (op from the closed vocabulary, open payload,
    no tags). The session adjudicates it; the contest never asserts a final number.
    """

    op: EffectOp
    payload: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    """One surfaced rule, ~ a matched rider clause: prose plus an optional effect.

    ``claim`` is the mandatory prose a dumb host reads; ``effect`` is the optional
    structured enhancement a host can mechanize. A claim-only Claim is valid.
    """

    claim: str
    effect: ClaimEffect | None = None
```

## The Contest message (`messages.py`)

```python
from face_dancer.protocol.contest import Claim


class Contest(Envelope):
    """Character-surfaced claims, not verdicts (character -> session)."""

    type: Literal["contest"] = "contest"
    claims: list[Claim] = Field(default_factory=list)
```

`Claim` and `ClaimEffect` are re-exported from `protocol/__init__.py` (added to
`__all__`, kept sorted).

## Testing

Extend `tests/test_protocol/`:

1. **Round-trip:** a `Contest` carrying a claim-only `Claim` **and** a `Claim` with
   a `ClaimEffect` (a real `EffectOp` + payload) round-trips `validate → serialize
   → parse` (python + JSON).
2. **`ClaimEffect.op` is closed:** a `ClaimEffect` with an op outside `EffectOp`
   (e.g. `"teleport"`) raises a validation error; a valid op parses to the enum.
3. **Claim-only is valid:** `Claim(claim="I resist fire")` has `effect is None`.
4. **Verdict-unrepresentable field guards:** `set(Claim.model_fields) == {"claim",
   "effect"}` and `set(ClaimEffect.model_fields) == {"op", "payload"}` — no
   result/total/verdict field can be added silently.
5. **Schema:** regenerate `docs/protocol/schema.json`; the `test_schema.py`
   assertions (six-member tagged union, discriminator mapping, committed == export)
   pass.
6. **Update existing fixtures:** the `Contest(claims=["…"])` constructions in
   `test_messages.py` (`_one_of_each`) and `test_validation.py` become
   `claims=[Claim(claim="…")]`.
7. **Public API:** `face_dancer.protocol` re-exports `Claim`, `ClaimEffect`.

All code passes `mypy --strict` and the existing ruff config.

## Out of scope

- The **rider matcher** (#23) that *populates* a contest from fired clauses
  (mapping `RiderEffect` → `ClaimEffect`).
- The **session's adjudication** of a contest into a final `apply_delta`.
- Any `request_roll` / `roll_result` interaction (a save surfaced in a claim is
  prose/effect here; the roll pair is its own issue).
- A `SCHEMA_VERSION` bump.
