# Vocabulary Spike (starter tags + closed effect-ops) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Codify the protocol's two starter vocabularies — a closed `EffectOp` enum (6 ops) and an open, documented tag vocabulary seeded from D&D 5e — in a new `vocabulary.py` leaf module, re-exported from the protocol package.

**Architecture:** A pure leaf module `src/face_dancer/protocol/vocabulary.py` with no intra-package imports, mirroring the conventions of `version.py`/`errors.py`. `EffectOp` is a closed `StrEnum` (adding a member is a `SCHEMA_VERSION` bump). Tags stay `frozenset[str]` on the wire; the module exports `DAMAGE_TYPES`, `CONDITIONS`, `STARTER_TAGS` as documented-guidance constants only. No message/schema changes — `SCHEMA_VERSION` stays `1`.

**Tech Stack:** Python 3.11+ (`enum.StrEnum`), pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-11-vocabulary-spike-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest` imports the main tree and will NOT see this worktree's new `vocabulary` module. **Every** test/mypy command below sets the path to this worktree's `src`:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ... ` (run from the worktree root)
- Types: `MYPYPATH="$PWD/src" mypy src`

---

## Task 1: The `vocabulary.py` module (EffectOp + tag constants)

**Files:**
- Create: `src/face_dancer/protocol/vocabulary.py`
- Test: `tests/test_protocol/test_vocabulary.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_protocol/test_vocabulary.py`:

```python
"""Tests for the closed effect-op enum and the starter tag vocabulary."""

import json

from face_dancer.protocol.vocabulary import (
    CONDITIONS,
    DAMAGE_TYPES,
    STARTER_TAGS,
    EffectOp,
)


def test_effect_op_members_are_exactly_the_closed_set() -> None:
    # Drift guard: changing the closed set must deliberately edit this test.
    assert {op.value for op in EffectOp} == {
        "reduce",
        "scale",
        "negate",
        "grant_save",
        "modify_roll",
        "replace",
    }


def test_effect_op_is_string_valued() -> None:
    assert EffectOp.REDUCE == "reduce"
    assert EffectOp("modify_roll") is EffectOp.MODIFY_ROLL
    # StrEnum serializes to the plain string in JSON.
    assert json.dumps(EffectOp.GRANT_SAVE) == '"grant_save"'


def test_damage_types_are_canonical_5e() -> None:
    assert DAMAGE_TYPES == frozenset(
        {
            "acid",
            "bludgeoning",
            "cold",
            "fire",
            "force",
            "lightning",
            "necrotic",
            "piercing",
            "poison",
            "psychic",
            "radiant",
            "slashing",
            "thunder",
        }
    )
    assert len(DAMAGE_TYPES) == 13


def test_conditions_are_canonical_5e() -> None:
    assert CONDITIONS == frozenset(
        {
            "blinded",
            "charmed",
            "deafened",
            "exhaustion",
            "frightened",
            "grappled",
            "incapacitated",
            "invisible",
            "paralyzed",
            "petrified",
            "poisoned",
            "prone",
            "restrained",
            "stunned",
            "unconscious",
        }
    )
    assert len(CONDITIONS) == 15


def test_damage_types_and_conditions_are_disjoint() -> None:
    # "poison" (damage type) and "poisoned" (condition) are intentionally distinct.
    assert DAMAGE_TYPES.isdisjoint(CONDITIONS)


def test_starter_tags_is_the_union() -> None:
    assert STARTER_TAGS == DAMAGE_TYPES | CONDITIONS
    assert len(STARTER_TAGS) == 28
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_vocabulary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.protocol.vocabulary'`.

- [ ] **Step 3: Write the module**

Create `src/face_dancer/protocol/vocabulary.py`:

```python
"""The protocol's closed effect-op set and starter tag vocabulary.

Two shared vocabularies the delta schemas and the rider matcher draw on:

- ``EffectOp`` is **closed and versioned** — the mechanical verbs every host's
  executor must understand. Adding a member changes the wire contract and is a
  ``SCHEMA_VERSION`` bump (see ``version.py``). Pressure to add a conditional
  *inside* an op is the signal that the clause is a ``judgment`` rider clause,
  not a richer op — the set stays closed.
- The **tag vocabulary is open**: a delta's ``tags`` field stays
  ``frozenset[str]`` on the wire. The constants below are a documented v0 starter
  set seeded from canonical D&D 5e, for authoring, tests, and rider matching —
  NOT a wire constraint. A non-5e host brings its own tags with no protocol
  change.
"""

from enum import StrEnum


class EffectOp(StrEnum):
    """The closed, versioned set of effect operations a delta may carry."""

    REDUCE = "reduce"  # subtract from a resource (e.g. HP)
    SCALE = "scale"  # multiply a magnitude (resistance ½, vulnerability ×2)
    NEGATE = "negate"  # cancel the effect entirely (immunity)
    GRANT_SAVE = "grant_save"  # offer a saving throw not otherwise present
    MODIFY_ROLL = "modify_roll"  # adjust a roll (advantage, flat bonus)
    REPLACE = "replace"  # substitute one effect for another


# Starter tag vocabulary (v0), seeded from canonical D&D 5e. Documented guidance,
# not a wire constraint — the wire type for a delta's ``tags`` stays
# ``frozenset[str]``.

DAMAGE_TYPES: frozenset[str] = frozenset(
    {
        "acid",
        "bludgeoning",
        "cold",
        "fire",
        "force",
        "lightning",
        "necrotic",
        "piercing",
        "poison",
        "psychic",
        "radiant",
        "slashing",
        "thunder",
    }
)

CONDITIONS: frozenset[str] = frozenset(
    {
        "blinded",
        "charmed",
        "deafened",
        "exhaustion",
        "frightened",
        "grappled",
        "incapacitated",
        "invisible",
        "paralyzed",
        "petrified",
        "poisoned",
        "prone",
        "restrained",
        "stunned",
        "unconscious",
    }
)

STARTER_TAGS: frozenset[str] = DAMAGE_TYPES | CONDITIONS
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_vocabulary.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint, format, and type-check**

Run:
```bash
ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src
```
Expected: `All checks passed!`, `... files already formatted`, `Success: no issues found`.
(If `ruff format --check` flags the new files, run `ruff format src tests` and re-run the check.)

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/protocol/vocabulary.py tests/test_protocol/test_vocabulary.py
git commit -m "feat(protocol): add closed EffectOp enum + starter tag vocabulary (issue #3)"
```

---

## Task 2: Re-export the vocabulary from the protocol package

**Files:**
- Modify: `src/face_dancer/protocol/__init__.py`
- Test: `tests/test_protocol/test_vocabulary.py` (add one test)

- [ ] **Step 1: Add the failing public-API test**

Append to `tests/test_protocol/test_vocabulary.py`:

```python
def test_public_api_is_reexported() -> None:
    import face_dancer.protocol as protocol

    for name in ("EffectOp", "DAMAGE_TYPES", "CONDITIONS", "STARTER_TAGS"):
        assert hasattr(protocol, name), f"protocol package does not re-export {name}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol/test_vocabulary.py::test_public_api_is_reexported -v`
Expected: FAIL — `AssertionError: protocol package does not re-export EffectOp`.

- [ ] **Step 3: Add the re-exports**

In `src/face_dancer/protocol/__init__.py`, add the import **last** in the
`from face_dancer.protocol.*` block — module order is alphabetical (`envelope`,
`errors`, `messages`, `validation`, `version`, `vocabulary`), so it goes after
the `version` import. Within the import, the three constants precede the
`EffectOp` class (ruff isort `order-by-type`):

```python
from face_dancer.protocol.version import SCHEMA_VERSION
from face_dancer.protocol.vocabulary import (
    CONDITIONS,
    DAMAGE_TYPES,
    STARTER_TAGS,
    EffectOp,
)
```

Then add these four names to the `__all__` list, keeping it alphabetically
sorted. After the edit `__all__` is:

```python
__all__ = [
    "CONDITIONS",
    "DAMAGE_TYPES",
    "MESSAGE_TYPES",
    "SCHEMA_VERSION",
    "STARTER_TAGS",
    "ApplyDelta",
    "Contest",
    "EffectOp",
    "Envelope",
    "Intent",
    "Message",
    "ProposeDelta",
    "ProtocolError",
    "RequestRoll",
    "RollResult",
    "SchemaVersionError",
    "UnknownMessageType",
    "export_schema",
    "validate",
]
```

- [ ] **Step 4: Run the full protocol test suite to verify it passes**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_protocol -v`
Expected: PASS (all prior protocol tests + 7 vocabulary tests).

- [ ] **Step 5: Lint, format, type-check, and run the whole suite**

Run:
```bash
ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src \
  && PYTHONPATH="$PWD/src" python3 -m pytest -q
```
Expected: all clean; full suite green (existing 65 + 7 new = 72 passing).

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/protocol/__init__.py tests/test_protocol/test_vocabulary.py
git commit -m "feat(protocol): re-export vocabulary public API (issue #3)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q          # 72 passed
ruff check src tests                                 # All checks passed!
ruff format --check src tests                        # all files formatted
MYPYPATH="$PWD/src" mypy src                          # Success: no issues found
python3 -c "import sys; sys.path.insert(0,'src'); \
  from face_dancer.protocol import EffectOp, STARTER_TAGS; \
  print(sorted(o.value for o in EffectOp)); print(len(STARTER_TAGS))"
# ['grant_save','modify_roll','negate','reduce','replace','scale']
# 28
```

## Out of scope (do NOT implement)

- The `op: EffectOp` field on `propose_delta`/`apply_delta` — issue #11.
- The rider matcher (op + tag-set comparison) — the rider issue.
- Any `SCHEMA_VERSION` change or wire-validation of tags against the starter set.
