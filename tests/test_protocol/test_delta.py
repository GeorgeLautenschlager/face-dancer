"""Tests for the Delta model — the shared (op, tags, payload) effect shape."""

import pytest
from pydantic import ValidationError

from face_dancer.protocol.delta import Delta
from face_dancer.protocol.vocabulary import EffectOp


def test_delta_defaults_to_empty_tags_and_payload() -> None:
    d = Delta(op=EffectOp.REDUCE)
    assert d.op is EffectOp.REDUCE
    assert d.tags == frozenset()
    assert d.payload == {}


def test_delta_round_trips_through_python_and_json() -> None:
    d = Delta(op=EffectOp.REDUCE, tags=frozenset({"fire"}), payload={"amount": 8})
    assert Delta.model_validate(d.model_dump()) == d
    assert Delta.model_validate_json(d.model_dump_json()) == d


def test_delta_op_accepts_a_known_op_string() -> None:
    d = Delta.model_validate({"op": "grant_save"})
    assert d.op is EffectOp.GRANT_SAVE


def test_delta_rejects_an_unknown_op() -> None:
    with pytest.raises(ValidationError):
        Delta.model_validate({"op": "teleport"})
