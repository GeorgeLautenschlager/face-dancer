"""Tests for the roll engine: code rolls the d20 and applies the modifier."""

import random
from uuid import uuid4

import pytest

from face_dancer.membrane import (
    ModelCallForbidden,
    ModelGateway,
    recorded_model_calls,
)
from face_dancer.protocol import EffectOp, RequestRoll, RollResult
from face_dancer.resolution import roll
from face_dancer.rider import Clause, Rider, RiderEffect, Trigger
from face_dancer.sheet import Sheet


def _request(kind: str = "perception", dc: int | None = None) -> RequestRoll:
    return RequestRoll(correlation_id=uuid4(), kind=kind, dc=dc)


def _modify_roll_clause(
    *, tags: set[str], bonus: int | None = None, op: EffectOp = EffectOp.MODIFY_ROLL
) -> Clause:
    payload: dict[str, int] = {} if bonus is None else {"bonus": bonus}
    return Clause(
        claim="roll modifier",
        trigger=Trigger(tags=frozenset(tags)),
        kind="mechanical",
        source="test",
        effect=RiderEffect(op=op, payload=payload),
    )


# --- determinism / arithmetic (AC4) ---


def test_seeded_roll_is_deterministic_natural_13() -> None:
    # random.Random(0).randint(1, 20) == 13
    result = roll(_request(), Sheet(), Rider(), rng=random.Random(0))
    assert result.natural == 13
    assert result.modifier == 0
    assert result.total == 13


def test_same_seed_is_repeatable() -> None:
    req = _request(kind="stealth")
    sheet, rider = Sheet(modifiers={"stealth": 2}), Rider()
    a = roll(req, sheet, rider, rng=random.Random(7))
    b = roll(req, sheet, rider, rng=random.Random(7))
    assert (a.natural, a.modifier, a.total) == (b.natural, b.modifier, b.total)
    assert a.modifier == 2


def test_total_integrity_over_a_seed_sweep() -> None:
    sheet = Sheet(modifiers={"athletics": 3})
    for seed in range(50):
        r = roll(_request(kind="athletics"), sheet, Rider(), rng=random.Random(seed))
        assert r.total == r.natural + r.modifier
        assert 1 <= r.natural <= 20
        assert r.modifier == 3


# --- modifier sourcing ---


def test_sheet_only_modifier() -> None:
    sheet = Sheet(modifiers={"perception": 4})
    r = roll(_request(kind="perception"), sheet, Rider(), rng=random.Random(0))
    assert r.modifier == 4
    assert r.total == 17  # 13 + 4


def test_absent_kind_gives_zero_modifier() -> None:
    r = roll(_request(kind="unknown_kind"), Sheet(), Rider(), rng=random.Random(0))
    assert r.modifier == 0
    assert r.total == r.natural


def test_rider_flat_bonus_added_on_kind_match() -> None:
    sheet = Sheet(modifiers={"perception": 1})
    rider = Rider(clauses=[_modify_roll_clause(tags={"perception"}, bonus=2)])
    r = roll(_request(kind="perception"), sheet, rider, rng=random.Random(0))
    assert r.modifier == 3  # sheet 1 + rider 2
    assert r.total == 16  # 13 + 3


def test_rider_non_matching_kind_ignored() -> None:
    rider = Rider(clauses=[_modify_roll_clause(tags={"stealth"}, bonus=5)])
    r = roll(_request(kind="perception"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 0


def test_non_modify_roll_effect_ignored() -> None:
    rider = Rider(clauses=[_modify_roll_clause(tags={"perception"}, bonus=5, op=EffectOp.REDUCE)])
    r = roll(_request(kind="perception"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 0


def test_modify_roll_without_bonus_contributes_zero() -> None:
    # An advantage-style payload (no "bonus" key) contributes 0 in v0.
    rider = Rider(clauses=[_modify_roll_clause(tags={"perception"}, bonus=None)])
    r = roll(_request(kind="perception"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 0


def test_empty_tag_clause_is_a_global_bonus() -> None:
    rider = Rider(clauses=[_modify_roll_clause(tags=set(), bonus=1)])
    r = roll(_request(kind="anything"), Sheet(), rider, rng=random.Random(0))
    assert r.modifier == 1
    assert r.total == 14  # 13 + 1


def test_negative_modifier_validates() -> None:
    sheet = Sheet(modifiers={"strength_save": -1})
    r = roll(_request(kind="strength_save"), sheet, Rider(), rng=random.Random(0))
    assert r.modifier == -1
    assert r.total == 12  # 13 - 1
    assert isinstance(r, RollResult)


# --- contract: correlation + dc ---


def test_correlation_id_is_preserved() -> None:
    req = _request()
    r = roll(req, Sheet(), Rider(), rng=random.Random(0))
    assert r.correlation_id == req.correlation_id


def test_dc_is_ignored() -> None:
    sheet = Sheet(modifiers={"perception": 2})
    with_dc = roll(
        RequestRoll(correlation_id=uuid4(), kind="perception", dc=15),
        sheet,
        Rider(),
        rng=random.Random(3),
    )
    blind = roll(
        RequestRoll(correlation_id=uuid4(), kind="perception", dc=None),
        sheet,
        Rider(),
        rng=random.Random(3),
    )
    assert (with_dc.natural, with_dc.modifier, with_dc.total) == (
        blind.natural,
        blind.modifier,
        blind.total,
    )


# --- model-free (AC5) ---


def test_roll_makes_no_model_call() -> None:
    with recorded_model_calls() as rec:
        roll(_request(), Sheet(), Rider(), rng=random.Random(0))
    assert rec.calls == []


def test_model_call_on_roll_path_is_forbidden() -> None:
    class _Probe(ModelGateway):
        def _invoke(self, request: object) -> object:
            return None

    gateway = _Probe()

    class _SneakySheet(Sheet):
        def modifier(self, kind: str) -> int:
            gateway.invoke("roll.sheet.modifier", None)
            return 0

    with pytest.raises(ModelCallForbidden):
        roll(_request(), _SneakySheet(), Rider(), rng=random.Random(0))


# --- public API ---


def test_public_api_is_reexported() -> None:
    import types

    import face_dancer.resolution as resolution

    assert "roll" in resolution.__all__
    assert callable(resolution.roll)
    # the re-export is the function, not the submodule of the same name
    assert not isinstance(resolution.roll, types.ModuleType)
