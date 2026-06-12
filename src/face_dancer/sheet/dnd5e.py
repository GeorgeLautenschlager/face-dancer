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
