# Roll Engine — Code Does the Dice & Arithmetic

**Issue:** [#20](https://github.com/GeorgeLautenschlager/face-dancer/issues/20)
**Date:** 2026-06-14
**Status:** Approved

## Purpose

Brief §4/§5 — the LLM must stay off the critical path for arithmetic; **code does
every roll and calculation**. Given a `request_roll`, the roll engine rolls the
die and applies the character's own modifier (sourced from the sheet and rider),
producing a `roll_result` whose `total` equals `natural + modifier`. The model is
never on this path.

This issue builds the engine that turns a `request_roll` into a `roll_result`. It
consumes the #14 messages and the #16 sheet, and reads the #18 rider for
roll-modifying clauses.

## Decisions

- **One function, `roll(request, sheet, rider, *, rng=None) -> RollResult`**, in a
  new `resolution/roll.py`. It returns a `RollResult` sharing the request's
  `correlation_id` — the result answers that exact request. `rng` is an injected
  `random.Random` (defaulting to a fresh `random.Random()`); a seeded instance is
  the **AC4 determinism hook** — same seed yields the same natural roll and total.

- **The die is a d20.** `natural = rng.randint(1, 20)`. The `roll_result` shape —
  a single `natural` plus `modifier` and `total` — *is* the 5e d20 check/save
  shape. Multi-die damage rolls have a different shape (no single "natural") and a
  different message; they are out of scope. Other dice are deferred.

- **Modifier = sheet contribution + rider contribution.**
  - **Sheet:** `sheet.modifier(request.kind)` — the existing `Sheet` contract
    (returns `0` when the kind is absent).
  - **Rider:** a clause contributes when it has an `effect` with
    `op == EffectOp.MODIFY_ROLL` **and** `trigger.tags <= {request.kind}`; its
    contribution is `effect.payload.get("bonus", 0)`. The engine sums the
    contributions of all matching clauses.
  - `total = natural + modifier` — consistent by construction with the #14
    `RollResult` validator.

- **Rider→roll matching keys on `request.kind` as a single tag.** A
  `request_roll` carries only `kind` and `dc` (no tags/op), so the engine treats
  `{request.kind}` as the roll's tag-set and applies the rider's existing
  tag-subset rule (`trigger.tags <= {kind}`). `trigger.op` is **ignored** for roll
  matching — a roll has no op. This covers self-modifiers ("bonus on perception",
  "bonus on a save kind"); context-conditioned modifiers ("advantage on saves vs
  poison", where `poison` rides on the *originating delta*, not the roll) are
  **not** handled here — they flow through `contest` / session adjudication later
  (#26). An **empty-tag** `MODIFY_ROLL` clause (`trigger.tags == frozenset()`)
  satisfies `<= {kind}` for every roll, so it is the natural "+1 to all rolls"
  global modifier; this is the documented consequence of subset matching, not a
  special case.

- **Advantage / disadvantage is deferred (per #4).** In v0 the engine reads only a
  flat `payload["bonus"]`. A `MODIFY_ROLL` clause whose payload has no `bonus`
  (e.g. it encodes advantage) contributes `0` via `payload.get("bonus", 0)` and is
  otherwise ignored — no error. Advantage is contested separately and applied
  later.

- **The computation is model-free (AC5).** The whole body runs inside
  `model_calls_forbidden("roll engine is code-only")`, mirroring `auto_contest`
  (#23) and `apply` (#19). "No model on the roll path" is a property of the code,
  provable by wrapping a call in `recorded_model_calls()` and asserting the
  recorder is empty.

- **`request.dc` is ignored.** The DC is session-owned and the `roll_result`
  carries no verdict (the #4/#14 decision). The engine produces only the number;
  the session compares it to the DC.

## Architecture

A new leaf module in the existing (currently docstring-only) `resolution/`
package, re-exported from its `__init__.py`.

```
src/face_dancer/resolution/
├── __init__.py     # re-export `roll` (keep the existing module docstring)
├── apply.py        # (existing, #19) the apply_delta executor
└── roll.py         # NEW: roll()
```

Dependency direction: `roll.py` imports `RequestRoll`/`RollResult` and `EffectOp`
from `face_dancer.protocol`, `Sheet` from `face_dancer.sheet`, `Rider` from
`face_dancer.rider`, and `model_calls_forbidden` from `face_dancer.membrane`.
`resolution → protocol`/`sheet`/`rider`/`membrane`; no cycles (parallels how
`apply.py` depends on `protocol`/`membrane`/`state`).

## The engine (`resolution/roll.py`)

```python
"""The roll engine: code rolls the die and applies the character's modifier."""

import random

from face_dancer.membrane import model_calls_forbidden
from face_dancer.protocol import EffectOp, RequestRoll, RollResult
from face_dancer.rider import Rider
from face_dancer.sheet import Sheet


def _rider_bonus(kind: str, rider: Rider) -> int:
    """Sum flat MODIFY_ROLL bonuses whose trigger fires on a roll of this kind.

    A clause contributes when it carries a MODIFY_ROLL effect and its trigger tags
    are a subset of the roll's single-tag set ``{kind}``. The roll has no op, so
    ``trigger.op`` is not consulted; a non-flat (advantage) payload contributes 0.
    """
    roll_tags = {kind}
    total = 0
    for clause in rider.clauses:
        effect = clause.effect
        if (
            effect is not None
            and effect.op is EffectOp.MODIFY_ROLL
            and clause.trigger.tags <= roll_tags
        ):
            total += effect.payload.get("bonus", 0)
    return total


def roll(
    request: RequestRoll,
    sheet: Sheet,
    rider: Rider,
    *,
    rng: random.Random | None = None,
) -> RollResult:
    """Resolve a request_roll into a roll_result, model-free.

    Rolls a d20 and applies the character's own modifier (sheet + rider). The
    returned RollResult shares the request's correlation_id and satisfies
    ``total == natural + modifier``. Pass a seeded ``rng`` for deterministic tests.
    """
    rng = rng if rng is not None else random.Random()
    with model_calls_forbidden("roll engine is code-only"):
        natural = rng.randint(1, 20)
        modifier = sheet.modifier(request.kind) + _rider_bonus(request.kind, rider)
        return RollResult(
            correlation_id=request.correlation_id,
            natural=natural,
            modifier=modifier,
            total=natural + modifier,
        )
```

Re-exported from `resolution/__init__.py` (keep the docstring): `roll`.

## Testing

`tests/test_resolution/test_roll.py`:

1. **AC4 — determinism:** two `roll()` calls with `random.Random(seed)` of the
   same seed yield identical `natural`/`modifier`/`total`; a different seed can
   differ. (Use a fixed seed whose first `randint(1, 20)` is known, to assert the
   exact natural.)
2. **AC4 — total integrity over a sweep:** for a range of seeds,
   `result.total == result.natural + result.modifier` and `1 <= natural <= 20`.
3. **Sheet-only modifier:** with an empty `Rider()`, `modifier ==
   sheet.modifier(kind)`; with a sheet that has no entry for `kind` and an empty
   rider, `modifier == 0` (so `total == natural`).
4. **Rider flat bonus added:** a `MODIFY_ROLL` clause with `trigger.tags ==
   {kind}` and `payload={"bonus": 2}` raises `modifier` by 2 over the sheet
   contribution.
5. **Non-matching rider kind ignored:** a `MODIFY_ROLL` clause whose
   `trigger.tags` is a different kind (not a subset of `{kind}`) contributes 0.
6. **Non-MODIFY_ROLL / non-bonus clauses contribute 0:** a `REDUCE`-effect clause
   that would otherwise match, and a `MODIFY_ROLL` clause whose payload has no
   `bonus` (advantage placeholder), both leave `modifier` unchanged.
7. **Empty-tag global bonus:** a `MODIFY_ROLL` clause with `trigger.tags ==
   frozenset()` and `payload={"bonus": 1}` applies to any roll kind.
8. **Negative modifier:** a sheet modifier of `-1` (or a rider bonus of `-1`)
   yields `total == natural - 1`, and the `RollResult` validates.
9. **correlation_id is preserved:** `roll(request, ...).correlation_id ==
   request.correlation_id`.
10. **dc is ignored:** a `request` with `dc=15` and one with `dc=None` (same
    seed/kind/sheet/rider) produce the same `RollResult`.
11. **AC5 — model-free:** within `recorded_model_calls()`, `roll()` records no
    calls; and a `ModelGateway.invoke` attempted on the roll path raises
    `ModelCallForbidden` (the membrane guard is active inside `roll`).
12. **Public API:** `face_dancer.resolution` re-exports `roll`.

`tests/test_resolution/__init__.py` is created if absent. All code passes
`mypy --strict` and the existing ruff config.

## Out of scope

- **Advantage / disadvantage** and contested roll conditions — contested via
  `contest` (per #4); applied later by the resolution loop.
- **Context-conditioned rider modifiers** (e.g. "vs poison"), which need the
  originating delta's tags — deferred to the resolution loop (#26).
- **Multi-die / damage rolls** — a different message shape; not this issue.
- The **resolution loop** (#26) that sequences `request_roll`/`roll_result` into
  the spine and supplies the originating-delta context.
- The **real `ModelGateway` adapter** — still a brief non-goal; the engine needs
  no model at all.
