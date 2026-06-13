# contest Message Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `contest` message its real schema — a list of `Claim`s (prose `claim` + optional structured `ClaimEffect`) — with a verdict made structurally unrepresentable.

**Architecture:** A new leaf `protocol/contest.py` holds `ClaimEffect(op, payload)` and `Claim(claim, effect)`. `Contest`'s body changes from `claims: list[str]` to `claims: list[Claim]`. No result/verdict field anywhere; field-set guards pin the shapes. The published `docs/protocol/schema.json` is regenerated; `SCHEMA_VERSION` stays `1`.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-contest-message-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`
- Schema regen: `PYTHONPATH="$PWD/src" python3 -m face_dancer.protocol.validation`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **145 passed**.

---

## Task 1: The claim shapes (`protocol/contest.py`)

**Files:**
- Create: `src/face_dancer/protocol/contest.py`
- Modify: `src/face_dancer/protocol/__init__.py`
- Test: `tests/test_protocol/test_contest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_protocol/test_contest.py`:

```python
"""Tests for the contest claim shapes: Claim + ClaimEffect (claims, not verdicts)."""

import pytest
from pydantic import ValidationError

from face_dancer.protocol.contest import Claim, ClaimEffect
from face_dancer.protocol.vocabulary import EffectOp


def test_claim_only_is_valid() -> None:
    c = Claim(claim="I have fire resistance")
    assert c.effect is None


def test_claim_effect_op_is_closed() -> None:
    e = ClaimEffect.model_validate({"op": "scale", "payload": {"factor": 0.5}})
    assert e.op is EffectOp.SCALE
    with pytest.raises(ValidationError):
        ClaimEffect.model_validate({"op": "teleport"})


def test_claim_round_trips_through_python_and_json() -> None:
    c = Claim(
        claim="I resist fire",
        effect=ClaimEffect(op=EffectOp.SCALE, payload={"factor": 0.5}),
    )
    assert Claim.model_validate(c.model_dump()) == c
    assert Claim.model_validate_json(c.model_dump_json()) == c


def test_claim_field_set_has_no_verdict() -> None:
    assert set(Claim.model_fields) == {"claim", "effect"}


def test_claim_effect_field_set_has_no_verdict() -> None:
    # No result/total field: a contest can never assert "therefore 14".
    assert set(ClaimEffect.model_fields) == {"op", "payload"}


def test_public_api_is_reexported() -> None:
    import face_dancer.protocol as protocol

    assert hasattr(protocol, "Claim")
    assert hasattr(protocol, "ClaimEffect")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_contest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.protocol.contest'`.

- [ ] **Step 3: Write the contest module**

Create `src/face_dancer/protocol/contest.py`:

```python
"""The contest claim shapes: a surfaced rule (claim + optional structured effect).

A contest carries claims, not verdicts: each claim is prose the session reads,
plus an optional structured suggestion. There is no result field — a final number
is unrepresentable here.
"""

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

- [ ] **Step 4: Re-export from the package**

In `src/face_dancer/protocol/__init__.py`, add the import as the **first**
`from face_dancer.protocol.*` line (module order is alphabetical: `contest`,
`delta`, `envelope`, …):

```python
from face_dancer.protocol.contest import Claim, ClaimEffect
from face_dancer.protocol.delta import Delta
```

Then add `"Claim"` and `"ClaimEffect"` to `__all__`, kept sorted — they go between
`"ApplyDelta"` and `"Contest"`:

```python
    "ApplyDelta",
    "Claim",
    "ClaimEffect",
    "Contest",
    "Delta",
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_contest.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/protocol/contest.py src/face_dancer/protocol/__init__.py tests/test_protocol/test_contest.py
git commit -m "feat(protocol): add the contest Claim + ClaimEffect shapes (issue #12)"
```

---

## Task 2: Rebody the `Contest` message to carry `Claim`s

**Files:**
- Modify: `src/face_dancer/protocol/messages.py`
- Modify: `tests/test_protocol/test_messages.py`
- Modify: `tests/test_protocol/test_validation.py`
- Test: `tests/test_protocol/test_contest.py`

- [ ] **Step 1: Add the failing Contest round-trip test**

Append to `tests/test_protocol/test_contest.py`:

```python
def test_contest_round_trips_through_validate() -> None:
    from uuid import uuid4

    from face_dancer.protocol import Contest, validate

    msg = Contest(
        correlation_id=uuid4(),
        claims=[
            Claim(claim="I have fire resistance and a save"),
            Claim(
                claim="Half damage",
                effect=ClaimEffect(op=EffectOp.SCALE, payload={"factor": 0.5}),
            ),
        ],
    )
    assert validate(msg.model_dump()) == msg
    assert validate(msg.model_dump_json()) == msg
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_contest.py::test_contest_round_trips_through_validate -v`
Expected: FAIL — `ValidationError` (the current `Contest.claims` is `list[str]`, so a `Claim` object is rejected).

- [ ] **Step 3: Rebody `Contest` in `messages.py`**

In `src/face_dancer/protocol/messages.py`:

(a) Add the `Claim` import as the **first** `from face_dancer.protocol.*` line
(before `delta`):

```python
from face_dancer.protocol.contest import Claim
from face_dancer.protocol.delta import Delta
from face_dancer.protocol.envelope import Envelope
```

(b) Replace the `Contest` class body's `claims` field:

```python
class Contest(Envelope):
    """Character-surfaced claims, not verdicts (character -> session)."""

    type: Literal["contest"] = "contest"
    claims: list[Claim] = Field(default_factory=list)
```

Leave every other message type, the `Message` union, and `MESSAGE_TYPES` unchanged.

- [ ] **Step 4: Update the existing Contest fixtures**

(a) In `tests/test_protocol/test_messages.py`, add the import below the existing
`from face_dancer.protocol.messages import (...)` block:

```python
from face_dancer.protocol.contest import Claim
```

Change the `Contest(...)` line in `_one_of_each()` to:

```python
        Contest(correlation_id=cid, claims=[Claim(claim="I have fire resistance and a save")]),
```

(b) In `tests/test_protocol/test_validation.py`, add the same import near the other
`from face_dancer.protocol.*` imports:

```python
from face_dancer.protocol.contest import Claim
```

Change the parametrized `Contest(...)` line to:

```python
        Contest(correlation_id=uuid4(), claims=[Claim(claim="I have fire resistance")]),
```

- [ ] **Step 5: Run the protocol suite (expect schema drift to fail)**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol -q`
Expected: all pass EXCEPT `test_schema.py::test_committed_schema_matches_export`,
which FAILS because the committed `schema.json` no longer matches the new `Contest`
body. That is fixed in Task 3 — do not edit the test.

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/protocol/messages.py tests/test_protocol/test_messages.py \
        tests/test_protocol/test_validation.py tests/test_protocol/test_contest.py
git commit -m "feat(protocol): rebody contest to carry Claims (issue #12)"
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
This rewrites `docs/protocol/schema.json` (the module's `__main__` calls `write_schema(Path("docs/protocol/schema.json"))`).

- [ ] **Step 2: Verify the drift guard now passes**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_schema.py -v`
Expected: PASS (3 tests) — `test_committed_schema_matches_export` now matches.

- [ ] **Step 3: Sanity-check the new shapes landed in the schema**

Run:
```bash
PYTHONPATH="$PWD/src" python3 -c "
import json; s = json.load(open('docs/protocol/schema.json'))
print('Claim' in s['\$defs'], 'ClaimEffect' in s['\$defs'])
"
```
Expected: `True True`.

- [ ] **Step 4: Commit**

```bash
git add docs/protocol/schema.json
git commit -m "chore(protocol): regenerate published schema for contest body (issue #12)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~152 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from uuid import uuid4
from face_dancer.protocol import Contest, Claim, ClaimEffect, EffectOp, validate
m = Contest(correlation_id=uuid4(), claims=[
    Claim(claim='I resist fire', effect=ClaimEffect(op=EffectOp.SCALE, payload={'factor': 0.5}))])
print(validate(m.model_dump_json()) == m)
"
# True
```

## Out of scope (do NOT implement)

- The rider matcher (#23) that populates a contest from fired clauses.
- The session's adjudication of a contest into an apply_delta.
- Any request_roll / roll_result interaction; a `SCHEMA_VERSION` bump.
