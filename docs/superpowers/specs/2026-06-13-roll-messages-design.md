# request_roll / roll_result Messages

**Issue:** [#14](https://github.com/GeorgeLautenschlager/face-dancer/issues/14)
**Date:** 2026-06-13
**Status:** Approved

## Purpose

Brief §3 — a save or check may resolve via a `request_roll` / `roll_result`
pair, the optional resolution rider on a delta. The roll itself is computed in
code (#20, its own issue); this issue owns the **message shapes** and encodes the
DC-ownership decision from the #4 spike.

The #9 placeholders are already close; #14 hardens them: it makes "the agent never
asserts a DC" (#4) a structural property of `request_roll`, and "the model can
never fake a roll total" a structural property of `roll_result`.

## Decisions

- **`request_roll` DC is session-owned and optional; there is no
  character-asserted-DC field (the #4 decision).** `dc: int | None = None` — the
  session supplies it, and `None` is the "roll blind" case (the session withholds
  the DC, e.g. "roll perception, I'll tell you if you make it"). The schema has
  exactly one DC field, the session's; a **field-set drift-guard** pins
  `RequestRoll`'s fields so a character-asserted DC cannot be added silently. This
  is the spike's output: the schema has no place for a character DC. **Advantage /
  contested roll conditions are deferred** (per #4 they are contested separately;
  the roll engine #20 applies them).

- **`roll_result.total` is validated: a faked total is rejected.** A
  `model_validator(mode="after")` raises if `total != natural + modifier`. The
  roll engine (#20) computes the arithmetic; this validator guarantees no *other*
  path — including a model trying to author the message — can carry a
  self-consistent lie. `total` stays a real, readable wire field (matching the
  brief's "natural roll, modifier, total"); the integrity is a loud guard
  (`ValidationError`, which `validate()` wraps as `ProtocolError`), the analog of
  the contest's verdict-guard.

- **No schema / version change.** The validator adds no field, so the published
  JSON Schema is unchanged (no regeneration needed; the drift guard still passes).
  `SCHEMA_VERSION` stays `1`. The existing `RequestRoll(kind="saving_throw",
  dc=15)` / `RollResult(natural=12, modifier=3, total=15)` fixtures stay valid
  (`12 + 3 == 15`), so there is no fixture churn.

- **`kind` is an open string** — the check name (`"saving_throw"`,
  `"perception"`) is system-specific, like the open tag vocabulary; the schema
  does not enumerate it.

## Architecture

A change confined to `messages.py` (where `RequestRoll`/`RollResult` already live)
plus a focused test file. No new module.

```
src/face_dancer/protocol/
└── messages.py     # add model_validator import; add the RollResult total validator
```

## The change (`protocol/messages.py`)

Add `model_validator` to the pydantic import (currently `from pydantic import
Field`):

```python
from pydantic import Field, model_validator
```

`RequestRoll` is **entirely unchanged** — the #4 decision is already structural
(one session-owned `dc`, no character DC), and its docstring already states it.
**Its docstring must not change**, because pydantic emits the class docstring as
the schema `description`, and changing it would drift `schema.json`. The #4 "no
character DC" guarantee is added as a *test* (the field-set guard), not a code
edit:

```python
class RequestRoll(Envelope):
    """A save or check to resolve (session -> character). DC is session-owned."""

    type: Literal["request_roll"] = "request_roll"
    kind: str
    dc: int | None = None
```

`RollResult` gains the total validator. **Its docstring is left unchanged** (same
schema-stability reason); only the validator method is added:

```python
class RollResult(Envelope):
    """A rolled result; total == natural + modifier, computed in code elsewhere."""

    type: Literal["roll_result"] = "roll_result"
    natural: int
    modifier: int
    total: int

    @model_validator(mode="after")
    def _total_is_consistent(self) -> "RollResult":
        if self.total != self.natural + self.modifier:
            raise ValueError(
                f"total {self.total} != natural {self.natural} + modifier {self.modifier}"
            )
        return self
```

The other message types, the `Message` union, and `MESSAGE_TYPES` are unchanged.
Adding a `model_validator` does not change the JSON Schema (validators are not
reflected in it), and the docstrings are untouched, so `schema.json` is unchanged.

## Testing

`tests/test_protocol/test_roll.py`:

1. **`RollResult` round-trips a consistent result** (`validate(m.model_dump()) ==
   m`, python + JSON) for a result where `total == natural + modifier` (including a
   negative modifier, e.g. `natural=12, modifier=-2, total=10`).
2. **An inconsistent `total` is rejected:** constructing `RollResult(natural=1,
   modifier=0, total=99)` raises `ValidationError`; and `validate()` on a raw
   inconsistent `roll_result` dict raises `ProtocolError`.
3. **`RequestRoll` round-trips with a `dc` and with `dc=None`** through
   `validate()`.
4. **`RequestRoll` field-set guard (the #4 encoding):** `set(RequestRoll.model_
   fields) == {"type", "schema_version", "message_id", "correlation_id", "kind",
   "dc"}` — no character-asserted-DC field can be added silently.
5. **Schema unchanged:** the `test_schema.py` drift guard
   (`test_committed_schema_matches_export`) still passes with no regeneration.

The existing `RequestRoll`/`RollResult` fixtures in `test_messages.py` /
`test_validation.py` are already consistent and need no change. All code passes
`mypy --strict` and the existing ruff config.

## Out of scope

- The **roll engine** that *computes* the result (rolls the die, reads the
  sheet/rider modifier, fills `RollResult`) — issue #20.
- **Advantage / disadvantage** and contested roll conditions — contested via
  `contest` (per #4); applied by the roll engine.
- The **resolution loop** (#26) that sequences the roll pair into the spine.
- A `SCHEMA_VERSION` bump or schema regeneration.
