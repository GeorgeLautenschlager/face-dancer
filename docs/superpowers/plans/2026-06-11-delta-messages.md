# Delta Messages (propose_delta + apply_delta) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the #9 placeholder bodies of `propose_delta`/`apply_delta` with a shared, first-class `Delta(op, tags, payload)` model built on the closed `EffectOp` vocabulary.

**Architecture:** A new leaf module `src/face_dancer/protocol/delta.py` defines `Delta`; `messages.py`'s two delta messages compose it as `delta: Delta`; `__init__.py` re-exports `Delta`; the published `docs/protocol/schema.json` is regenerated. The `Message` union and the four other message types are untouched. `SCHEMA_VERSION` stays `1`.

**Tech Stack:** Python 3.11+, pydantic v2 (`StrEnum` op from `vocabulary.py`), pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-11-delta-messages-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree branched off the #3 spike branch. The
`face_dancer` package is editable-installed from the **main** checkout, so a bare
`pytest`/`mypy` imports the main tree and will NOT see this worktree's changes (or
`vocabulary.py`). **Every** command below sets the path to this worktree's `src`,
run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`
- Schema regen: `PYTHONPATH="$PWD/src" python3 -m face_dancer.protocol.validation`

---

## Task 1: The `Delta` model

**Files:**
- Create: `src/face_dancer/protocol/delta.py`
- Test: `tests/test_protocol/test_delta.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_protocol/test_delta.py`:

```python
"""Tests for the Delta model — the shared (op, tags, payload) effect shape."""

import pytest
from pydantic import ValidationError

from face_dancer.protocol.delta import Delta
from face_dancer.protocol.vocabulary import EffectOp


def test_delta_defaults_to_empty_tags_and_payload() -> None:
    d = Delta(op=EffectOp.REDUCE)
    assert d.op is EffectOp.REDUCE
    assert d.tags == frozenset()
    assert d.payload == {}


def test_delta_round_trips_through_python_and_json() -> None:
    d = Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"}), payload={"amount": 8})
    assert Delta.model_validate(d.model_dump()) == d
    assert Delta.model_validate_json(d.model_dump_json()) == d


def test_delta_op_accepts_a_known_op_string() -> None:
    d = Delta.model_validate({"op": "grant_save"})
    assert d.op is EffectOp.GRANT_SAVE


def test_delta_rejects_an_unknown_op() -> None:
    with pytest.raises(ValidationError):
        Delta.model_validate({"op": "teleport"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_delta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.protocol.delta'`.

- [ ] **Step 3: Write the module**

Create `src/face_dancer/protocol/delta.py`:

```python
"""The shared delta shape: one effect a propose/apply message carries.

A ``Delta`` is exactly one operation: a single ``op`` drawn from the closed
``EffectOp`` vocabulary, the tag-set it applies under (open ``frozenset[str]`` —
the rider matches on op + tag-set), and an open ``payload``. The per-op payload
schemas (what ``reduce`` carries vs. ``grant_save``) belong to the executor that
applies them; here the payload is carried, not asserted.
"""

from typing import Any

from pydantic import BaseModel, Field

from face_dancer.protocol.vocabulary import EffectOp


class Delta(BaseModel):
    """One effect: a single op, the tag-set it applies under, and its payload."""

    op: EffectOp
    tags: frozenset[str] = frozenset()
    payload: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_delta.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/protocol/delta.py tests/test_protocol/test_delta.py
git commit -m "feat(protocol): add the Delta model (op, tags, payload) (issue #11)"
```

---

## Task 2: Rebody the delta messages + re-export + update fixtures

**Files:**
- Modify: `src/face_dancer/protocol/messages.py`
- Modify: `src/face_dancer/protocol/__init__.py`
- Modify: `tests/test_protocol/test_messages.py`
- Modify: `tests/test_protocol/test_validation.py`

- [ ] **Step 1: Rebody `ProposeDelta` and `ApplyDelta`**

In `src/face_dancer/protocol/messages.py`:

(a) Change the typing import (drop now-unused `Any`) and add the `Delta` import. The import block becomes:

```python
from typing import Annotated, Literal, get_args

from pydantic import Field

from face_dancer.protocol.delta import Delta
from face_dancer.protocol.envelope import Envelope
```

(b) Replace the `ProposeDelta` and `ApplyDelta` class bodies with:

```python
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

Leave `Contest`, `Intent`, `RequestRoll`, `RollResult`, the `Message` union, and `MESSAGE_TYPES` exactly as they are.

- [ ] **Step 2: Re-export `Delta` from the package**

In `src/face_dancer/protocol/__init__.py`, add the import as the **first**
`from face_dancer.protocol.*` line (module order is alphabetical: `delta`,
`envelope`, `errors`, ...):

```python
from face_dancer.protocol.delta import Delta
```

Add `"Delta"` to `__all__`, keeping it sorted — it goes among the classes,
between `"Contest"` and `"EffectOp"`:

```python
    "ApplyDelta",
    "Contest",
    "Delta",
    "EffectOp",
    "Envelope",
```

- [ ] **Step 3: Update the broken fixtures**

(a) In `tests/test_protocol/test_messages.py`, add two imports below the existing
`from face_dancer.protocol.messages import (...)` block:

```python
from face_dancer.protocol.delta import Delta
from face_dancer.protocol.vocabulary import EffectOp
```

Then replace the `ProposeDelta(...)` and `ApplyDelta(...)` entries in
`_one_of_each()` with:

```python
        ProposeDelta(
            correlation_id=cid,
            delta=Delta(
                op=EffectOp.REDUCE, tags=frozenset({"fire"}), payload={"amount": 8}
            ),
        ),
        ApplyDelta(
            correlation_id=cid,
            delta=Delta(
                op=EffectOp.REDUCE, tags=frozenset({"fire"}), payload={"amount": 4}
            ),
        ),
```

(b) In `tests/test_protocol/test_validation.py`, add the same two imports near the
top (with the other `from face_dancer.protocol.*` imports):

```python
from face_dancer.protocol.delta import Delta
from face_dancer.protocol.vocabulary import EffectOp
```

Replace the three old-shape constructions:
- `test_validate_dispatches_on_discriminator` — change
  `msg = ProposeDelta(correlation_id=uuid4(), target="self")` to:
  ```python
  msg = ProposeDelta(correlation_id=uuid4(), delta=Delta(op=EffectOp.REDUCE))
  ```
- In the parametrized list near the bottom, change the two delta lines to:
  ```python
        ProposeDelta(
            correlation_id=uuid4(),
            delta=Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"})),
        ),
        ApplyDelta(correlation_id=uuid4(), delta=Delta(op=EffectOp.REDUCE)),
  ```

- [ ] **Step 4: Add an op-validation test through `validate()`**

Append to `tests/test_protocol/test_validation.py`:

```python
def test_validate_rejects_unknown_delta_op() -> None:
    # delta.op must be a known EffectOp; an unknown op is a body error.
    raw = {
        "type": "propose_delta",
        "correlation_id": str(uuid4()),
        "delta": {"op": "teleport"},
    }
    with pytest.raises(ProtocolError):
        validate(raw)
```

- [ ] **Step 5: Run the protocol suite (expect schema drift to fail)**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol -v`
Expected: all pass EXCEPT `test_schema.py::test_committed_schema_matches_export`,
which FAILS because the committed `schema.json` no longer matches the new delta
body. That failure is fixed in Task 3 — do not edit the test.

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/protocol/messages.py src/face_dancer/protocol/__init__.py \
        tests/test_protocol/test_messages.py tests/test_protocol/test_validation.py
git commit -m "feat(protocol): rebody propose/apply_delta to carry a Delta (issue #11)"
```

---

## Task 3: Regenerate the published JSON Schema

**Files:**
- Modify: `docs/protocol/schema.json`

- [ ] **Step 1: Regenerate the schema artifact**

Run from the worktree root:
```bash
PYTHONPATH="$PWD/src" python3 -m face_dancer.protocol.validation
```
This rewrites `docs/protocol/schema.json` (the module's `__main__` calls
`write_schema(Path("docs/protocol/schema.json"))`).

- [ ] **Step 2: Verify the drift guard now passes**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_schema.py -v`
Expected: PASS (3 tests) — `test_committed_schema_matches_export` now matches.

- [ ] **Step 3: Sanity-check the new shape landed in the schema**

Run:
```bash
PYTHONPATH="$PWD/src" python3 -c "import json; s=json.load(open('docs/protocol/schema.json')); \
print('Delta' in s.get('\$defs', {})); \
print('ProposeDelta' in s.get('\$defs', {}))"
```
Expected: `True` then `True` (the `Delta` model and the message reference it).

- [ ] **Step 4: Commit**

```bash
git add docs/protocol/schema.json
git commit -m "chore(protocol): regenerate published schema for delta body (issue #11)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~68 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "from face_dancer.protocol import Delta, ProposeDelta, EffectOp; \
  m = ProposeDelta(correlation_id=__import__('uuid').uuid4(), \
                   delta=Delta(op=EffectOp.REDUCE, tags=frozenset({'fire'}), payload={'amount': 8})); \
  from face_dancer.protocol import validate; print(validate(m.model_dump_json()) == m)"
# True
```

## Out of scope (do NOT implement)

- Per-op payload schemas (reduce vs grant_save internals) — executor/resolution issue.
- The rider matcher (op + tag-set comparison) — the rider issue.
- The apply executor (writing apply_delta into dynamic state) — its own issue.
- Any `contest` / `request_roll` / `roll_result` change, or a `SCHEMA_VERSION` bump.
