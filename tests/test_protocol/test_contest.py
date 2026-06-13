"""Tests for the contest claim shapes: Claim + ClaimEffect (claims, not verdicts)."""

import pytest
from pydantic import ValidationError

from face_dancer.protocol.contest import Claim, ClaimEffect
from face_dancer.protocol.vocabulary import EffectOp


def test_claim_only_is_valid() -> None:
    c = Claim(claim="I have fire resistance")
    assert c.effect is None


def test_claim_effect_op_is_closed() -> None:
    e = ClaimEffect.model_validate({"op": "scale", "payload": {"factor": 0.5}})
    assert e.op is EffectOp.SCALE
    with pytest.raises(ValidationError):
        ClaimEffect.model_validate({"op": "teleport"})


def test_claim_round_trips_through_python_and_json() -> None:
    c = Claim(
        claim="I resist fire",
        effect=ClaimEffect(op=EffectOp.SCALE, payload={"factor": 0.5}),
    )
    assert Claim.model_validate(c.model_dump()) == c
    assert Claim.model_validate_json(c.model_dump_json()) == c


def test_claim_field_set_has_no_verdict() -> None:
    assert set(Claim.model_fields) == {"claim", "effect"}


def test_claim_effect_field_set_has_no_verdict() -> None:
    # No result/total field: a contest can never assert "therefore 14".
    assert set(ClaimEffect.model_fields) == {"op", "payload"}


def test_public_api_is_reexported() -> None:
    import face_dancer.protocol as protocol

    assert hasattr(protocol, "Claim")
    assert hasattr(protocol, "ClaimEffect")
