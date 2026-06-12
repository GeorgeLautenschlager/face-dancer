"""Tests for the Capability model and its intent feed."""

from uuid import uuid4

from face_dancer.capability.capability import Capability
from face_dancer.protocol import Intent


def test_defaults_to_empty_tags() -> None:
    cap = Capability(name="cast fireball", description="hurl a bolt of flame")
    assert cap.name == "cast fireball"
    assert cap.description == "hurl a bolt of flame"
    assert cap.tags == frozenset()


def test_keeps_tags() -> None:
    cap = Capability(name="cast fireball", description="x", tags=frozenset({"fire"}))
    assert cap.tags == frozenset({"fire"})


def test_round_trips_through_python_and_json() -> None:
    cap = Capability(name="cast fireball", description="x", tags=frozenset({"fire"}))
    assert Capability.model_validate(cap.model_dump()) == cap
    assert Capability.model_validate_json(cap.model_dump_json()) == cap


def test_to_intent_uses_name_as_action() -> None:
    cap = Capability(name="cast fireball", description="x")
    cid = uuid4()
    intent = cap.to_intent(correlation_id=cid)
    assert isinstance(intent, Intent)
    assert intent.action == "cast fireball"
    assert intent.correlation_id == cid
    assert intent.target is None
    assert intent.narration is None


def test_to_intent_carries_target_and_narration() -> None:
    cap = Capability(name="cast fireball", description="x")
    intent = cap.to_intent(
        correlation_id=uuid4(), target="goblin", narration="Melian hurls a fireball."
    )
    assert intent.target == "goblin"
    assert intent.narration == "Melian hurls a fireball."


def test_capability_has_no_legality_field() -> None:
    # The character declares what it CAN do, never what is legal now. A legality /
    # availability field must be a deliberate edit that trips this guard.
    assert set(Capability.model_fields) == {"name", "description", "tags"}


def test_public_api_is_reexported() -> None:
    import face_dancer.capability as capability

    assert hasattr(capability, "Capability")
