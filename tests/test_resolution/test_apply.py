"""Tests for the apply_delta executor — the sole, model-free writer to state."""

from uuid import uuid4

import pytest

from face_dancer.bundle import Bundle
from face_dancer.membrane import Applied, recorded_model_calls
from face_dancer.protocol import ApplyDelta, Delta, EffectOp
from face_dancer.resolution.apply import ApplyError, apply
from face_dancer.state import DynamicState


def _msg(op: EffectOp, payload: dict[str, object]) -> ApplyDelta:
    return ApplyDelta(correlation_id=uuid4(), delta=Delta(op=op, payload=payload))


def test_reduce_hp_mutates_state_with_no_model_call() -> None:
    state = DynamicState(hp=20)
    with recorded_model_calls() as rec:
        result = apply(_msg(EffectOp.REDUCE, {"target": "hp", "amount": 8}), state)
    assert state.hp == 12
    assert rec.calls == []  # AC5: no model on the apply path
    assert isinstance(result, Applied)  # membrane write-proof


def test_reduce_resource_defaults_absent_key_to_zero() -> None:
    state = DynamicState()
    apply(_msg(EffectOp.REDUCE, {"target": "resources", "key": "ki", "amount": 1}), state)
    assert state.resources["ki"] == -1


def test_change_persists_through_a_bundle_round_trip() -> None:
    # AC2: after apply, persisted state reflects the change.
    bundle = Bundle(name="Fighter", state=DynamicState(hp=20))
    apply(_msg(EffectOp.REDUCE, {"target": "hp", "amount": 5}), bundle.state)
    reloaded = Bundle.deserialize(bundle.serialize())
    assert reloaded.state.hp == 15


def test_adjudication_op_is_rejected() -> None:
    state = DynamicState(hp=20)
    with pytest.raises(ApplyError):
        apply(_msg(EffectOp.SCALE, {"target": "hp", "factor": 0.5}), state)


def test_unknown_target_raises() -> None:
    state = DynamicState(hp=20)
    with pytest.raises(ApplyError):
        apply(_msg(EffectOp.REDUCE, {"target": "mana", "amount": 1}), state)


def test_missing_payload_field_raises() -> None:
    state = DynamicState(hp=20)
    with pytest.raises(ApplyError):
        apply(_msg(EffectOp.REDUCE, {"target": "hp"}), state)


def test_public_api_is_reexported() -> None:
    import face_dancer.resolution as resolution

    assert hasattr(resolution, "apply")
    assert hasattr(resolution, "ApplyError")
