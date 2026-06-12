# Intent Message (character-side opener) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the `intent` message from the #9 placeholder (`action: str`) into the real schema — `action` + optional `target` + optional `narration` — carrying no assertion of legality.

**Architecture:** `Intent` is a member of the message union, so its body is expanded inline in `messages.py` (no new module). `action`/`target` are the simple host-understood contract; `narration` is optional expressive flair the session never parses for mechanics. The published `docs/protocol/schema.json` is regenerated. `SCHEMA_VERSION` stays `1` (the new fields are optional and defaulted).

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-11-intent-message-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`
- Schema regen: `PYTHONPATH="$PWD/src" python3 -m face_dancer.protocol.validation`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **82 passed**.

---

## Task 1: Expand the `Intent` body + tests

**Files:**
- Modify: `src/face_dancer/protocol/messages.py` (the `Intent` class, currently lines 40-44)
- Test: `tests/test_protocol/test_intent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_protocol/test_intent.py`:

```python
"""Tests for the intent message — the character-side opener."""

from uuid import uuid4

import pytest

from face_dancer.protocol.errors import ProtocolError
from face_dancer.protocol.messages import Intent
from face_dancer.protocol.validation import validate


def test_action_only_round_trips() -> None:
    msg = Intent(correlation_id=uuid4(), action="cast fireball")
    assert validate(msg.model_dump()) == msg
    assert validate(msg.model_dump_json()) == msg


def test_full_intent_round_trips() -> None:
    msg = Intent(
        correlation_id=uuid4(),
        action="cast fireball",
        target="goblin",
        narration="With only the barest hint of contempt, Melian hurls a fireball at the goblin.",
    )
    assert validate(msg.model_dump()) == msg
    assert validate(msg.model_dump_json()) == msg


def test_target_and_narration_default_to_none() -> None:
    msg = Intent(correlation_id=uuid4(), action="take cover")
    assert msg.target is None
    assert msg.narration is None


def test_action_is_required() -> None:
    raw = {"type": "intent", "correlation_id": str(uuid4())}
    with pytest.raises(ProtocolError):
        validate(raw)


def test_intent_carries_no_legality_field() -> None:
    # Field-set drift guard: the intent asserts no legality. Adding a legality
    # field (valid/legal/dc/...) must be a deliberate edit that trips this test.
    assert set(Intent.model_fields) == {
        "type",
        "schema_version",
        "message_id",
        "correlation_id",
        "action",
        "target",
        "narration",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_intent.py -v`
Expected: FAIL — `test_full_intent_round_trips` errors (`Intent` has no `target`/`narration`) and `test_intent_carries_no_legality_field` fails (field set lacks `target`/`narration`).

- [ ] **Step 3: Expand the `Intent` class**

In `src/face_dancer/protocol/messages.py`, replace the entire `Intent` class with:

```python
class Intent(Envelope):
    """Character-side opener; the session adjudicates it into a propose_delta.

    ``action`` and ``target`` are the simple, host-understood contract the session
    reads and adjudicates; the character names a target but never asserts its
    legality (affordance is session-owned). ``narration`` is optional in-character
    flair the session may render but never parses for mechanics.
    """

    type: Literal["intent"] = "intent"
    action: str
    target: str | None = None
    narration: str | None = None
```

Leave every other message type, the `Message` union, and `MESSAGE_TYPES` unchanged.

- [ ] **Step 4: Run the Intent tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_intent.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the protocol suite (expect schema drift to fail)**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol -q`
Expected: all pass EXCEPT `test_schema.py::test_committed_schema_matches_export`,
which FAILS because the committed `schema.json` no longer matches the new `Intent`
body. That is fixed in Task 2 — do not edit the test. (The existing `action`-only
`Intent` fixtures in `test_messages.py` / `test_validation.py` still pass.)

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new test file, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/protocol/messages.py tests/test_protocol/test_intent.py
git commit -m "feat(protocol): expand intent with target + narration (issue #13)"
```

---

## Task 2: Regenerate the published JSON Schema

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

- [ ] **Step 3: Sanity-check the new fields landed in the schema**

Run:
```bash
PYTHONPATH="$PWD/src" python3 -c "
import json; s = json.load(open('docs/protocol/schema.json'))
intent = s['\$defs']['Intent']['properties']
print('target' in intent, 'narration' in intent)
"
```
Expected: `True True`.

- [ ] **Step 4: Commit**

```bash
git add docs/protocol/schema.json
git commit -m "chore(protocol): regenerate published schema for intent body (issue #13)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~87 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from uuid import uuid4
from face_dancer.protocol import Intent, validate
m = Intent(correlation_id=uuid4(), action='cast fireball', target='goblin',
           narration='Melian hurls a fireball at the goblin.')
print(validate(m.model_dump_json()) == m)
"
# True
```

## Out of scope (do NOT implement)

- The capability schema / action interface (#22) — `action` stays an open string.
- Perception / target resolution (#21) — `target` is a bare name, not resolved/validated.
- Session-side adjudication of an intent into a propose_delta.
- A `parameters` field, or any legality field, or a `SCHEMA_VERSION` bump.
