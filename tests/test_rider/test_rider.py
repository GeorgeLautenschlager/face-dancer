"""Tests for the rules-rider schema: clauses, triggers, and the reactive fence."""

import pytest
from pydantic import ValidationError

from face_dancer.protocol import EffectOp
from face_dancer.rider.rider import Clause, Rider, RiderEffect, Trigger


def test_claim_only_clause_is_valid() -> None:
    c = Clause(
        claim="I have fire resistance",
        trigger=Trigger(tags=frozenset({"fire"})),
        kind="mechanical",
        source="PHB p.1",
    )
    assert c.effect is None
    assert c.order is None


def test_trigger_is_required() -> None:
    with pytest.raises(ValidationError):
        Clause(claim="x", kind="mechanical", source="x")


def test_trigger_op_optional_tags_required() -> None:
    assert Trigger(tags=frozenset({"fire"})).op is None
    with pytest.raises(ValidationError):
        Trigger()


def test_effect_op_is_closed() -> None:
    e = RiderEffect.model_validate({"op": "scale", "payload": {"factor": 0.5}})
    assert e.op is EffectOp.SCALE
    with pytest.raises(ValidationError):
        RiderEffect.model_validate({"op": "teleport"})


def test_clause_field_set_is_the_fence() -> None:
    # Reactive only: no capability/stat field can be added silently.
    assert set(Clause.model_fields) == {
        "claim",
        "trigger",
        "kind",
        "source",
        "effect",
        "order",
    }


def test_rider_round_trips() -> None:
    rider = Rider(
        clauses=[
            Clause(
                claim="Half damage from fire",
                trigger=Trigger(tags=frozenset({"fire"}), op=EffectOp.REDUCE),
                kind="mechanical",
                source="race: tiefling",
                effect=RiderEffect(op=EffectOp.SCALE, payload={"factor": 0.5}),
                order=1,
            ),
            Clause(
                claim="I argue I should get a save vs this",
                trigger=Trigger(tags=frozenset({"charm"})),
                kind="judgment",
                source="homebrew",
            ),
        ]
    )
    assert Rider.model_validate(rider.model_dump()) == rider
    assert Rider.model_validate_json(rider.model_dump_json()) == rider


def test_rider_defaults_empty() -> None:
    assert Rider().clauses == []


def test_public_api_is_reexported() -> None:
    import face_dancer.rider as rider

    for name in ("Rider", "Clause", "Trigger", "RiderEffect"):
        assert hasattr(rider, name)
