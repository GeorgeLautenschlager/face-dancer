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
