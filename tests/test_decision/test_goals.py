"""Tests for the three-timescale Goals model."""

from face_dancer.decision.goals import Goals


def test_defaults_are_the_fallback() -> None:
    g = Goals()
    assert g.persistent_drives == []
    assert g.situational_objectives == []  # empty = the #6 fallback (no inference)
    assert g.tactical_intent is None


def test_round_trips_through_python_and_json() -> None:
    g = Goals(
        persistent_drives=["protect the weak"],
        situational_objectives=["reach the bridge"],
        tactical_intent="flank the archer",
    )
    assert Goals.model_validate(g.model_dump()) == g
    assert Goals.model_validate_json(g.model_dump_json()) == g


def test_public_api_is_reexported() -> None:
    import face_dancer.decision as decision

    assert hasattr(decision, "Goals")
