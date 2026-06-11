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
    # The count assertion trips an accidental addition independently of the values.
    assert len(EffectOp) == 6
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
    assert (
        frozenset(
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
        == DAMAGE_TYPES
    )
    assert len(DAMAGE_TYPES) == 13


def test_conditions_are_canonical_5e() -> None:
    assert (
        frozenset(
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
        == CONDITIONS
    )
    assert len(CONDITIONS) == 15


def test_damage_types_and_conditions_are_disjoint() -> None:
    # "poison" (damage type) and "poisoned" (condition) are intentionally distinct.
    assert DAMAGE_TYPES.isdisjoint(CONDITIONS)


def test_starter_tags_is_the_union() -> None:
    assert STARTER_TAGS == DAMAGE_TYPES | CONDITIONS
    assert len(STARTER_TAGS) == 28


def test_public_api_is_reexported() -> None:
    import face_dancer.protocol as protocol

    for name in ("EffectOp", "DAMAGE_TYPES", "CONDITIONS", "STARTER_TAGS"):
        assert hasattr(protocol, name), f"protocol package does not re-export {name}"
