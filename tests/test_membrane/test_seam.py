"""Tests for the propose/dispose seam: the model proposes, only code disposes."""

import pytest

from face_dancer.membrane.instrumentation import ModelCallForbidden, NullModelGateway
from face_dancer.membrane.seam import Applied, MembraneViolation, Proposal, dispose


def test_dispose_runs_disposer_and_wraps_result() -> None:
    proposal = Proposal(payload=7, origin="model")

    def halve(damage: int) -> int:
        return damage // 2

    applied = dispose(proposal, halve)
    assert isinstance(applied, Applied)
    assert applied.result == 3
    # the proposal is inert and untouched; provenance survives disposal
    assert proposal.payload == 7
    assert proposal.origin == "model"


def test_applied_cannot_be_minted_outside_dispose() -> None:
    with pytest.raises(MembraneViolation):
        Applied(42)


def test_applied_rejects_forged_tokens() -> None:
    with pytest.raises(MembraneViolation):
        Applied(42, object())


def test_dispose_is_a_model_free_region() -> None:
    gateway = NullModelGateway()
    proposal = Proposal(payload="drink potion", origin="model")

    def disposer_that_cheats(payload: str) -> str:
        gateway.invoke("seam.disposal", payload)
        return payload

    with pytest.raises(ModelCallForbidden):
        dispose(proposal, disposer_that_cheats)
