# Sheet Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the generic, frozen `Sheet` (opaque stats + a structured modifiers contract), type the bundle's `sheet` slot with it, and add a 5e reference producer that computes a `Sheet` from 5e inputs.

**Architecture:** A new `sheet/` package: `Sheet` (system-agnostic; the roll engine reads `modifier(kind)`) and `dnd5e.from_5e()` (a *producer* of `Sheet`s — nothing in core imports it). The bundle's `sheet` field changes from `dict[str, Any]` to `Sheet`. `BUNDLE_SCHEMA_VERSION` stays 1.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-12-sheet-artifact-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **87 passed**.

---

## Task 1: The generic `Sheet` (new `sheet/` package)

**Files:**
- Create: `src/face_dancer/sheet/__init__.py`, `src/face_dancer/sheet/sheet.py`
- Test: `tests/test_sheet/__init__.py`, `tests/test_sheet/test_sheet.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sheet/__init__.py` as an **empty file** (package marker).

Create `tests/test_sheet/test_sheet.py`:

```python
"""Tests for the generic Sheet: stats + the modifier contract, read-only."""

import pytest
from pydantic import ValidationError

from face_dancer.sheet.sheet import Sheet


def test_defaults_are_empty() -> None:
    s = Sheet()
    assert s.stats == {}
    assert s.modifiers == {}


def test_modifier_accessor_returns_value_or_zero() -> None:
    s = Sheet(modifiers={"athletics": 5})
    assert s.modifier("athletics") == 5
    assert s.modifier("unknown") == 0


def test_round_trips_through_python_and_json() -> None:
    s = Sheet(stats={"ac": 15}, modifiers={"dexterity_save": 5})
    assert Sheet.model_validate(s.model_dump()) == s
    assert Sheet.model_validate_json(s.model_dump_json()) == s


def test_sheet_is_frozen() -> None:
    s = Sheet(modifiers={"athletics": 5})
    with pytest.raises(ValidationError):
        s.modifiers = {}


def test_public_api_is_reexported() -> None:
    import face_dancer.sheet as sheet

    assert hasattr(sheet, "Sheet")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_sheet/test_sheet.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.sheet'`.

- [ ] **Step 3: Write the `Sheet` model**

Create `src/face_dancer/sheet/sheet.py`:

```python
"""The generic, read-only character sheet: opaque stats + a modifier contract."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Sheet(BaseModel):
    """The character's static, read-only sheet: opaque stats + a modifier contract.

    ``stats`` is the host/system-defined stat block (ability scores, max HP, AC,
    proficiencies — whatever the system uses); the character carries it but the
    core never interprets it. ``modifiers`` is the structured contract the roll
    engine consumes via ``modifier()``. The sheet is frozen — read-only at runtime.
    """

    model_config = ConfigDict(frozen=True)

    stats: dict[str, Any] = Field(default_factory=dict)
    modifiers: dict[str, int] = Field(default_factory=dict)

    def modifier(self, kind: str) -> int:
        """Return the modifier the roll engine should apply for ``kind`` (0 if absent)."""
        return self.modifiers.get(kind, 0)
```

- [ ] **Step 4: Write the package `__init__.py`**

Create `src/face_dancer/sheet/__init__.py`:

```python
"""Character sheet — static identity and stats (read-only at runtime).

A system-agnostic base: opaque ``stats`` plus a structured ``modifiers`` contract
the roll engine consumes. System-specific producers (e.g. ``dnd5e``) compute a
Sheet; nothing in the core depends on them.
"""

from face_dancer.sheet.sheet import Sheet

__all__ = ["Sheet"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_sheet/test_sheet.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/sheet/__init__.py src/face_dancer/sheet/sheet.py tests/test_sheet
git commit -m "feat(sheet): add generic Sheet with modifier contract (issue #16)"
```

---

## Task 2: Type the bundle's `sheet` slot

**Files:**
- Modify: `src/face_dancer/bundle/container.py`
- Modify: `tests/test_bundle/test_bundle.py`

- [ ] **Step 1: Change the bundle's `sheet` field to the typed `Sheet`**

In `src/face_dancer/bundle/container.py`:

(a) Add the import — it sorts among the `face_dancer.*` imports (`bundle.errors`, `bundle.version`, `sheet`, `state`); place it after the bundle imports and before `state`:

```python
from face_dancer.bundle.errors import BundleError, BundleVersionError
from face_dancer.bundle.version import BUNDLE_SCHEMA_VERSION
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState
```

(b) Change the `sheet` field (leave `rider` as `dict[str, Any]`, so the `Any` import stays):

```python
    sheet: Sheet = Field(default_factory=Sheet)
```

- [ ] **Step 2: Update the existing bundle fixtures for the typed sheet**

In `tests/test_bundle/test_bundle.py`:

(a) Add the import below the existing `from face_dancer.state import DynamicState` import:

```python
from face_dancer.sheet import Sheet
```

(b) In `test_construction`, change the empty-sheet assertion:

```python
    assert bundle.sheet == Sheet()
```
(leave `assert bundle.rider == {}` unchanged).

(c) In `test_construction_with_values`, change the `sheet` value and its assertion
(a dict for `sheet` is coerced into a `Sheet`; unknown keys are ignored, so pass
the typed `stats` shape):

```python
    sheet = {"stats": {"strength": 10}}
```
and:
```python
    assert bundle.sheet == Sheet(stats={"strength": 10})
```
(`rider` remains a dict; leave its assertion unchanged.)

(d) In `test_round_trip_populated`, change the `sheet={"attr": 1}` line so the
sheet is genuinely populated (the bare `{"attr": 1}` would be dropped as an
unknown key):

```python
        sheet={"stats": {"attr": 1}},
```

(e) In `test_load_unload_reload`, change the `sheet={"a": 1}` argument likewise:

```python
    original = Bundle(name="Persistence Test", sheet={"stats": {"a": 1}})
```

- [ ] **Step 3: Run the bundle suite (and full suite)**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_bundle -v`
Expected: PASS. (`test_round_trip_populated` now round-trips a populated `Sheet`, covering the bundle-with-sheet persistence.)

- [ ] **Step 4: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 5: Commit**

```bash
git add src/face_dancer/bundle/container.py tests/test_bundle/test_bundle.py
git commit -m "feat(bundle): persist typed Sheet in the sheet slot (issue #16)"
```

---

## Task 3: The 5e reference producer

**Files:**
- Create: `src/face_dancer/sheet/dnd5e.py`
- Test: `tests/test_sheet/test_dnd5e.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sheet/test_dnd5e.py`:

```python
"""Tests for the 5e reference producer: derived ability/save/skill modifiers."""

from face_dancer.sheet.dnd5e import ability_modifier, from_5e
from face_dancer.sheet.sheet import Sheet


def test_ability_modifier_math() -> None:
    assert ability_modifier(14) == 2
    assert ability_modifier(10) == 0
    assert ability_modifier(8) == -1
    assert ability_modifier(7) == -2  # floors on negatives


def _sample() -> Sheet:
    return from_5e(
        ability_scores={
            "strength": 14,
            "dexterity": 16,
            "constitution": 12,
            "intelligence": 10,
            "wisdom": 13,
            "charisma": 8,
        },
        proficiency_bonus=2,
        max_hp=24,
        ac=15,
        proficient_saves=frozenset({"dexterity", "constitution"}),
        proficient_skills=frozenset({"athletics", "perception"}),
    )


def test_produces_a_sheet() -> None:
    assert isinstance(_sample(), Sheet)


def test_ability_modifiers_present() -> None:
    s = _sample()
    assert s.modifier("strength") == 2
    assert s.modifier("dexterity") == 3
    assert s.modifier("charisma") == -1


def test_proficient_vs_non_proficient_saves() -> None:
    s = _sample()
    assert s.modifier("dexterity_save") == 5  # dex mod 3 + prof 2
    assert s.modifier("strength_save") == 2  # str mod 2, not proficient


def test_skill_modifiers() -> None:
    s = _sample()
    assert s.modifier("athletics") == 4  # STR mod 2 + prof 2 (proficient)
    assert s.modifier("perception") == 3  # WIS mod 1 + prof 2 (proficient)
    assert s.modifier("acrobatics") == 3  # DEX mod 3, not proficient


def test_stats_block_populated() -> None:
    s = _sample()
    assert s.stats["max_hp"] == 24
    assert s.stats["ac"] == 15
    assert s.stats["proficiency_bonus"] == 2
    assert s.stats["ability_scores"]["dexterity"] == 16
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_sheet/test_dnd5e.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.sheet.dnd5e'`.

- [ ] **Step 3: Write the 5e producer**

Create `src/face_dancer/sheet/dnd5e.py`:

```python
"""5e reference producer: compute a generic Sheet from 5e inputs.

A *producer* of the system-agnostic Sheet — nothing in the core imports this.
Other systems add their own producers; the Sheet contract is unchanged.
"""

from typing import Any

from face_dancer.sheet.sheet import Sheet

ABILITIES = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)

# canonical 5e skill -> governing ability (18 skills)
SKILL_ABILITY: dict[str, str] = {
    "athletics": "strength",
    "acrobatics": "dexterity",
    "sleight_of_hand": "dexterity",
    "stealth": "dexterity",
    "arcana": "intelligence",
    "history": "intelligence",
    "investigation": "intelligence",
    "nature": "intelligence",
    "religion": "intelligence",
    "animal_handling": "wisdom",
    "insight": "wisdom",
    "medicine": "wisdom",
    "perception": "wisdom",
    "survival": "wisdom",
    "deception": "charisma",
    "intimidation": "charisma",
    "performance": "charisma",
    "persuasion": "charisma",
}


def ability_modifier(score: int) -> int:
    """The 5e ability modifier for a score (floor division matches 5e's floor)."""
    return (score - 10) // 2


def from_5e(
    *,
    ability_scores: dict[str, int],
    proficiency_bonus: int,
    max_hp: int,
    ac: int,
    proficient_saves: frozenset[str] = frozenset(),
    proficient_skills: frozenset[str] = frozenset(),
) -> Sheet:
    """Produce a generic Sheet from 5e inputs, computing the derived modifiers."""
    modifiers: dict[str, int] = {}
    for ability in ABILITIES:
        am = ability_modifier(ability_scores[ability])
        modifiers[ability] = am
        bonus = proficiency_bonus if ability in proficient_saves else 0
        modifiers[f"{ability}_save"] = am + bonus
    for skill, ability in SKILL_ABILITY.items():
        am = ability_modifier(ability_scores[ability])
        bonus = proficiency_bonus if skill in proficient_skills else 0
        modifiers[skill] = am + bonus

    stats: dict[str, Any] = {
        "ability_scores": dict(ability_scores),
        "max_hp": max_hp,
        "ac": ac,
        "proficiency_bonus": proficiency_bonus,
        "proficient_saves": sorted(proficient_saves),
        "proficient_skills": sorted(proficient_skills),
    }
    return Sheet(stats=stats, modifiers=modifiers)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_sheet/test_dnd5e.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/sheet/dnd5e.py tests/test_sheet/test_dnd5e.py
git commit -m "feat(sheet): add 5e reference producer for derived modifiers (issue #16)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~98 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from face_dancer.sheet.dnd5e import from_5e
from face_dancer.bundle import Bundle
s = from_5e(ability_scores={'strength':14,'dexterity':16,'constitution':12,
            'intelligence':10,'wisdom':13,'charisma':8},
            proficiency_bonus=2, max_hp=24, ac=15,
            proficient_saves=frozenset({'dexterity'}),
            proficient_skills=frozenset({'athletics'}))
b = Bundle(name='Fighter', sheet=s)
print(s.modifier('dexterity_save'), s.modifier('athletics'))
print(Bundle.deserialize(b.serialize()).sheet == s)
"
# 5 4
# True
```

## Out of scope (do NOT implement)

- The roll engine that consumes `sheet.modifier()` — its own issue.
- Other systems' producers; spells/feats/equipment; AC-from-armor; HP-from-class.
- Deep-immutable dicts (frozen covers field reassignment); any write path to the sheet.
- A `BUNDLE_SCHEMA_VERSION` bump.
