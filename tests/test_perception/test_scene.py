"""Tests for the perceivable-scene payload."""

from face_dancer.perception.scene import Entity, PerceptionCheck, Scene


def test_entity_defaults() -> None:
    e = Entity(name="goblin")
    assert e.description == ""
    assert e.perceivable_with == frozenset()
    assert e.check is None


def test_scene_round_trips_through_python_and_json() -> None:
    scene = Scene(
        description="A torchlit cavern.",
        entities=[
            Entity(name="goblin", description="snarling"),
            Entity(
                name="imp",
                perceivable_with=frozenset({"truesight"}),
                check=PerceptionCheck(kind="perception", dc=15),
            ),
        ],
    )
    assert Scene.model_validate(scene.model_dump()) == scene
    assert Scene.model_validate_json(scene.model_dump_json()) == scene
