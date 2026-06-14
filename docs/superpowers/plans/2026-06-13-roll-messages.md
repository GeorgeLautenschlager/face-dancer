# request_roll / roll_result Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the `request_roll` / `roll_result` placeholders so the #4 DC-ownership decision and roll-total integrity are structural: `roll_result.total` must equal `natural + modifier`, and `request_roll` can never carry a character-asserted DC.

**Architecture:** A single change confined to `protocol/messages.py` — add a `model_validator(mode="after")` to `RollResult` that rejects an inconsistent total — plus a focused test file. `RequestRoll` and both docstrings are left untouched (pydantic emits class docstrings as schema `description`, so editing them would drift `schema.json`); the #4 "no character DC" guarantee is added as a field-set test, not a code edit. A validator adds no field, so the published JSON Schema is unchanged and `SCHEMA_VERSION` stays `1`.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-roll-messages-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **164 passed**.

The existing fixtures (`RequestRoll(kind="saving_throw", dc=15)` and `RollResult(natural=12, modifier=3, total=15)`, where `12 + 3 == 15`) are already consistent, so there is **no fixture churn** — do not edit `test_messages.py` or `test_validation.py`.

---

## Task 1: The roll-total validator + roll tests

**Files:**
- Modify: `src/face_dancer/protocol/messages.py`
- Test: `tests/test_protocol/test_roll.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_protocol/test_roll.py`:

```python
"""Tests for the roll message pair: request_roll (session-owned DC) and
roll_result (total integrity)."""

import pytest
from pydantic import ValidationError

from face_dancer.protocol import RequestRoll, RollResult, validate
from face_dancer.protocol.errors import ProtocolError


def test_roll_result_round_trips_through_validate() -> None:
    m = RollResult(natural=12, modifier=3, total=15)
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_roll_result_round_trips_with_negative_modifier() -> None:
    m = RollResult(natural=12, modifier=-2, total=10)
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_inconsistent_total_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        RollResult(natural=1, modifier=0, total=99)


def test_inconsistent_total_through_validate_raises_protocol_error() -> None:
    from uuid import uuid4

    raw = {
        "type": "roll_result",
        "schema_version": 1,
        "message_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "natural": 1,
        "modifier": 0,
        "total": 99,
    }
    with pytest.raises(ProtocolError):
        validate(raw)


def test_request_roll_round_trips_with_dc() -> None:
    m = RequestRoll(kind="saving_throw", dc=15)
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_request_roll_round_trips_blind_with_dc_none() -> None:
    m = RequestRoll(kind="perception")
    assert m.dc is None
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_request_roll_field_set_has_no_character_dc() -> None:
    # The #4 encoding: the only DC field is the session's `dc`. No
    # character-asserted-DC field can be added silently.
    assert set(RequestRoll.model_fields) == {
        "type",
        "schema_version",
        "message_id",
        "correlation_id",
        "kind",
        "dc",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_roll.py -v`
Expected: the four `RollResult`/`validate` *integrity* tests behave thus —
`test_inconsistent_total_raises_validation_error` and
`test_inconsistent_total_through_validate_raises_protocol_error` **FAIL** (no
validator yet, so an inconsistent total is currently accepted). The round-trip and
field-set tests already pass (the message shapes are in place).

- [ ] **Step 3: Add the validator to `RollResult`**

In `src/face_dancer/protocol/messages.py`:

(a) Add `model_validator` to the pydantic import (line 10 is currently
`from pydantic import Field`):

```python
from pydantic import Field, model_validator
```

(b) Add the validator method to the `RollResult` class body (leave its docstring
and the three fields **exactly** as they are):

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

Leave `RequestRoll`, every other message type, the `Message` union, and
`MESSAGE_TYPES` unchanged. Do **not** edit any class docstring (they are emitted as
the schema `description`; changing one would drift `schema.json`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_roll.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Confirm the schema did not drift**

A validator adds no field, so the published JSON Schema is unchanged. Verify the
drift guard still passes with **no regeneration**:

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_schema.py -v`
Expected: PASS (3 tests) — `test_committed_schema_matches_export` still matches.
If it fails, do **not** regenerate the schema; a docstring was edited by mistake —
revert the docstring instead.

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new test file, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/protocol/messages.py tests/test_protocol/test_roll.py
git commit -m "feat(protocol): validate roll_result total + pin request_roll DC ownership (issue #14)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~171 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
import pytest
from pydantic import ValidationError
from face_dancer.protocol import RollResult, RequestRoll, validate
print(validate(RollResult(natural=12, modifier=-2, total=10).model_dump_json()))
print(RequestRoll(kind='perception').dc)   # None -> roll blind
try:
    RollResult(natural=1, modifier=0, total=99)
except ValidationError:
    print('rejected faked total')
"
# roll_result ... natural=12 modifier=-2 total=10
# None
# rejected faked total
```

## Out of scope (do NOT implement)

- The **roll engine** that *computes* the result (rolls the die, reads the
  sheet/rider modifier, fills `RollResult`) — issue #20.
- **Advantage / disadvantage** and contested roll conditions — contested via
  `contest` (per #4); applied by the roll engine.
- The **resolution loop** (#26) that sequences the roll pair into the spine.
- A `SCHEMA_VERSION` bump or schema regeneration (the validator changes no field).
- Any edit to existing `test_messages.py` / `test_validation.py` fixtures (already consistent).
