# Sheet Artifact — Generic Contract + 5e Reference Builder

**Issue:** [#16](https://github.com/GeorgeLautenschlager/face-dancer/issues/16)
**Date:** 2026-06-12
**Status:** Approved

## Purpose

Brief §3 — the **sheet** holds static identity and stats: ability scores, max HP,
AC, modifiers, proficiencies. Static stats live here; *proactive* capabilities
live in the action interface (#22) and *reactive* rules live in the rider (#18).
The sheet is **read-only at runtime** (no writes during play), and its one hard
contract is that it **exposes its modifiers to downstream code** — specifically
the roll engine (brief AC §9: "the character rolls using its own modifier *from
the sheet*").

This issue builds the sheet as an **extensible, system-agnostic base** with a
**5e reference implementation** layered on top — the design direction is to ship
structures that support 5e out of the box while keeping the core generic, so the
same character can later play in other systems (or a video game) by adding more
producers, not by changing the core.

## Decisions

- **The generic `Sheet` is the system-agnostic contract: opaque `stats` + a
  structured `modifiers` map.** `stats: dict[str, Any]` is host/system-defined
  (ability scores, AC, max HP, proficiencies — whatever the system uses);
  `modifiers: dict[str, int]` is the roll-engine contract, read via a
  `modifier(kind) -> int` accessor (returns `0` for an unknown kind). Everything
  downstream depends on this generic type; nothing downstream reads `stats`.
  Chosen over a 5e-typed sheet (which would bake one rule system into the core)
  per the opaque-artifacts direction: the host owns system knowledge, so the
  character declares its modifiers rather than the sheet deriving them from 5e
  rules.

- **5e is a *producer*, not a dependency.** The 5e reference builder
  (`sheet/dnd5e.py`) takes 5e inputs and *computes* a generic `Sheet`; nothing in
  the core imports it. Other systems (or a video-game host) are additional
  producers of the same `Sheet`. This makes the "same character, any system"
  promise structural — the genericity is enforced by the dependency direction,
  not aspirational.

- **The `Sheet` is frozen (read-only at runtime).** `model_config =
  ConfigDict(frozen=True)` — no field reassignment during play, satisfying the
  DoD's "immutable during a turn." (Caveat: pydantic `frozen` blocks reassigning
  the *fields*, not deep-mutating the dict *contents*; true deep-immutability is
  deferred. `frozen` enforces the "no writes to the sheet" intent at the field
  level, and contrasts deliberately with the mutable `DynamicState`.)

- **No `name` field on the `Sheet`.** The character's name lives on `Bundle.name`;
  richer 5e identity (race/class/level) rides in opaque `stats`. The sheet is
  *stats + modifiers*, matching the brief's concrete list (all stats). This also
  lets `Bundle.sheet` default to an empty `Sheet()`.

- **`modifier` kind naming is the producer's choice.** The 5e builder keys
  modifiers `"strength"`, `"strength_save"`, `"athletics"`, … The generic `Sheet`
  does not enforce these names — a different system's producer picks its own; the
  roll engine and the sheet agree on a kind string, the sheet never validates it.

- **5e reference scope: core derivation.** Ability modifiers `(score - 10) // 2`
  (Python floor division matches 5e's floor, incl. negatives: 8 → −1); save
  modifiers (`ability_mod + proficiency_bonus` if proficient); skill modifiers via
  the canonical 18-skill → ability map (`+ proficiency_bonus` if proficient). AC
  and max HP are passed in (not computed from armor/class). Spells, feats,
  equipment, AC-from-armor, and HP-from-class are deferred.

- **`Bundle.sheet` becomes the typed `Sheet`.** `sheet: dict[str, Any]` →
  `sheet: Sheet = Field(default_factory=Sheet)`, mirroring how #17 typed the
  `state` slot. The bundle round-trip persists it; `BUNDLE_SCHEMA_VERSION` stays
  `1` (an old `"sheet": {}` loads to an empty `Sheet`).

## Architecture

A new `sheet/` package; one field-type change in the bundle.

```
src/face_dancer/sheet/
├── __init__.py        # re-exports Sheet
├── sheet.py           # NEW: the generic Sheet (stats + modifiers + accessor, frozen)
└── dnd5e.py           # NEW: from_5e() — the 5e reference producer + skill map

src/face_dancer/bundle/
└── container.py       # Bundle.sheet: dict[str, Any] -> Sheet
```

Dependency direction: `sheet/sheet.py` imports only pydantic + stdlib;
`sheet/dnd5e.py` imports `Sheet` from `face_dancer.sheet`; `bundle/container.py`
imports `Sheet` from `face_dancer.sheet`. No cycles. The core (Sheet, bundle)
never imports `dnd5e`.

## The generic `Sheet` (`sheet/sheet.py`)

```python
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

Re-exported from `sheet/__init__.py` with `__all__ = ["Sheet"]`.

## Bundle integration (`container.py`)

```python
from face_dancer.sheet import Sheet

class Bundle(BaseModel):
    ...
    sheet: Sheet = Field(default_factory=Sheet)
    ...
```

`load`/`unload`/`deserialize` unchanged — pydantic validates the nested frozen
`Sheet` on parse and serializes it on dump. A dict passed for `sheet` is coerced
into a `Sheet` (unknown keys ignored), and an old `"sheet": {}` loads to an empty
`Sheet`.

## The 5e reference producer (`sheet/dnd5e.py`)

```python
ABILITIES = ("strength", "dexterity", "constitution",
             "intelligence", "wisdom", "charisma")

# canonical 5e skill -> governing ability (18 skills)
SKILL_ABILITY: dict[str, str] = {
    "athletics": "strength",
    "acrobatics": "dexterity", "sleight_of_hand": "dexterity", "stealth": "dexterity",
    "arcana": "intelligence", "history": "intelligence", "investigation": "intelligence",
    "nature": "intelligence", "religion": "intelligence",
    "animal_handling": "wisdom", "insight": "wisdom", "medicine": "wisdom",
    "perception": "wisdom", "survival": "wisdom",
    "deception": "charisma", "intimidation": "charisma",
    "performance": "charisma", "persuasion": "charisma",
}


def ability_modifier(score: int) -> int:
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
    mods: dict[str, int] = {}
    for ability in ABILITIES:
        am = ability_modifier(ability_scores[ability])
        mods[ability] = am
        mods[f"{ability}_save"] = am + (proficiency_bonus if ability in proficient_saves else 0)
    for skill, ability in SKILL_ABILITY.items():
        am = ability_modifier(ability_scores[ability])
        mods[skill] = am + (proficiency_bonus if skill in proficient_skills else 0)

    stats: dict[str, Any] = {
        "ability_scores": dict(ability_scores),
        "max_hp": max_hp,
        "ac": ac,
        "proficiency_bonus": proficiency_bonus,
        "proficient_saves": sorted(proficient_saves),
        "proficient_skills": sorted(proficient_skills),
    }
    return Sheet(stats=stats, modifiers=mods)
```

## Testing

`tests/test_sheet/test_sheet.py` (generic):

1. **Defaults / accessor:** `Sheet()` has empty `stats`/`modifiers`;
   `Sheet(modifiers={"athletics": 5}).modifier("athletics") == 5`;
   `.modifier("unknown") == 0`.
2. **Round-trip:** a populated `Sheet` round-trips python + JSON (`==`).
3. **Frozen:** assigning to a field (`sheet.modifiers = {}`) raises
   `ValidationError` (pydantic frozen).

`tests/test_sheet/test_dnd5e.py` (5e producer):

4. **Ability modifier math:** `ability_modifier(14) == 2`, `10 == 0`, `8 == -1`,
   `7 == -2` (floor on negatives).
5. **Non-proficient vs proficient save:** a DEX-save-proficient character's
   `sheet.modifier("dexterity_save") == dex_mod + proficiency_bonus`; a
   non-proficient save equals just the ability mod.
6. **Skill modifier:** `sheet.modifier("athletics") == strength_mod (+ prof if
   proficient)`.
7. **Stats populated:** the produced sheet's `stats` carries `ability_scores`,
   `max_hp`, `ac`, `proficiency_bonus`.

`tests/test_bundle/test_bundle.py` (integration):

8. **Bundle round-trip with a populated sheet** survives `unload → load` (`==`).
9. **Update existing fixtures** that pass `sheet={"strength": 10}` and assert
   against a raw dict to the typed `Sheet` shape.

`tests/test_sheet/__init__.py` empty package marker. All code passes
`mypy --strict` and the existing ruff config.

## Out of scope

- The **roll engine** (consumes `sheet.modifier()`) — its own issue.
- **Other systems' producers** — only the 5e reference here; the structure is the
  extension point.
- **Spells, feats, equipment, AC-from-armor, HP-from-class** — beyond core 5e
  derivation.
- **Deep-immutable dicts** — `frozen` covers field reassignment; deep immutability
  deferred.
- The **rider (#18)** and any write path to the sheet (there is none — read-only).
