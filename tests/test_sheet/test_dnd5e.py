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


def test_produced_sheet_round_trips() -> None:
    # Lock determinism through the producer path, not just hand-built sheets.
    s = _sample()
    assert Sheet.model_validate(s.model_dump()) == s
    assert Sheet.model_validate_json(s.model_dump_json()) == s
