"""Tests for the roll message pair: request_roll (session-owned DC) and
roll_result (total integrity)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from face_dancer.protocol import RequestRoll, RollResult, validate
from face_dancer.protocol.errors import ProtocolError


def test_roll_result_round_trips_through_validate() -> None:
    cid = uuid4()
    m = RollResult(correlation_id=cid, natural=12, modifier=3, total=15)
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_roll_result_round_trips_with_negative_modifier() -> None:
    cid = uuid4()
    m = RollResult(correlation_id=cid, natural=12, modifier=-2, total=10)
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_inconsistent_total_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        RollResult(correlation_id=uuid4(), natural=1, modifier=0, total=99)


def test_inconsistent_total_through_validate_raises_protocol_error() -> None:
    raw = {
        "type": "roll_result",
        "schema_version": 1,
        "message_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "natural": 1,
        "modifier": 0,
        "total": 99,
    }
    with pytest.raises(ProtocolError):
        validate(raw)


def test_request_roll_round_trips_with_dc() -> None:
    cid = uuid4()
    m = RequestRoll(correlation_id=cid, kind="saving_throw", dc=15)
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_request_roll_round_trips_blind_with_dc_none() -> None:
    cid = uuid4()
    m = RequestRoll(correlation_id=cid, kind="perception")
    assert m.dc is None
    assert validate(m.model_dump()) == m
    assert validate(m.model_dump_json()) == m


def test_request_roll_field_set_has_no_character_dc() -> None:
    # The #4 encoding: the only DC field is the session's `dc`. No
    # character-asserted-DC field can be added silently.
    assert set(RequestRoll.model_fields) == {
        "type",
        "schema_version",
        "message_id",
        "correlation_id",
        "kind",
        "dc",
    }
