"""Tests for the DynamicState model — the volatile, code-written state store."""

from face_dancer.state.dynamic_state import DynamicState


def test_defaults_are_blank() -> None:
    s = DynamicState()
    assert s.hp == 0
    assert s.conditions == set()
    assert s.resources == {}
    assert s.position is None


def test_round_trips_through_python_and_json() -> None:
    s = DynamicState(
        hp=18,
        conditions={"prone", "poisoned"},
        resources={"spell_slot_1": 3, "ki": 2},
        position={"x": 3, "y": 7},
    )
    assert DynamicState.model_validate(s.model_dump()) == s
    assert DynamicState.model_validate_json(s.model_dump_json()) == s


def test_code_mutates_in_place() -> None:
    s = DynamicState(hp=20)
    s.hp = 12
    s.conditions.add("prone")
    s.resources["ki"] = 1
    s.position = {"zone": "bridge"}
    assert s.hp == 12
    assert "prone" in s.conditions
    assert s.resources["ki"] == 1
    assert s.position == {"zone": "bridge"}


def test_public_api_is_reexported() -> None:
    import face_dancer.state as state

    assert hasattr(state, "DynamicState")
