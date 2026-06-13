# Rider Matcher + Mechanical Auto-Contest

**Issue:** [#23](https://github.com/GeorgeLautenschlager/face-dancer/issues/23)
**Date:** 2026-06-13
**Status:** Approved

## Purpose

Brief §5 — rider triggers match on **op + tag-set (all tags present)**, so one
mechanic ("anything fire") spans damage, conditions, and saves without enumerating
event shapes. The matcher is a **set comparison reusing the protocol's tag
vocabulary, not a parser**. `mechanical` clauses auto-contest **in code** (the
scarce model stays out of routine rules bookkeeping); a `claim`-only clause still
surfaces as prose (progressive enhancement).

This issue builds the matcher and the mechanical auto-contest: given a
`propose_delta` and the character's `Rider`, fire the matching clauses and emit a
`contest` for the mechanical ones — model-free.

## Decisions

- **`matches(delta, rider)` is the reusable matcher primitive.** A pure set
  comparison: a clause fires when **all** its trigger tags are present on the delta
  (`trigger.tags <= delta.tags`) **and** its op matches (`trigger.op is None` — the
  wildcard — or `trigger.op == delta.op`). It returns **all** firing clauses
  (mechanical *and* judgment), in rider-list order. #23 itself auto-contests only
  the mechanical ones; **#25 (judgment routing) reuses `matches`** to find the
  judgment clauses.

- **`auto_contest(propose, rider) -> Contest | None` is structurally model-free.**
  It runs inside the membrane's `model_calls_forbidden` region, so **AC1 ("without
  invoking the model") is a property of the path**, mirroring the apply executor
  (#19). It filters the matches to `kind == "mechanical"`, and:
  - returns `None` when no mechanical clause fires (the delta proceeds
    unchallenged), or
  - returns a `Contest` carrying the fired clauses' claims, sharing the propose's
    `correlation_id` (the contest responds to that exchange).

- **Progressive enhancement: a clause becomes a `Claim`.** `_to_claim` maps a
  clause's mandatory prose `claim` plus its optional `RiderEffect(op, payload)`
  onto a `Claim(claim, effect)`, where `effect` is a `ClaimEffect(op, payload)`
  (the protocol twin of `RiderEffect`) when the clause has a structured effect, and
  `None` otherwise. A **claim-only clause surfaces as prose** (`effect is None`) —
  **AC8**.

- **Judgment routing and `order` sequencing are out of scope.** Judgment clauses
  are *matched* (returned by `matches`) but not auto-contested here — routing one to
  a mind is #25. Claims surface in rider-list order; honoring a clause's `order`
  proposal is the resolution loop's concern.

## Architecture

A new module in the existing `rider/` package.

```
src/face_dancer/rider/
├── __init__.py     # re-exports Rider/Clause/Trigger/RiderEffect (existing) + matches, auto_contest
├── rider.py        # (existing) the schema
└── matcher.py      # NEW: matches(), auto_contest(), _to_claim()
```

Dependency direction: `matcher.py` imports `Rider`/`Clause` from
`face_dancer.rider.rider`, `ProposeDelta`/`Delta`/`Contest`/`Claim`/`ClaimEffect`
from `face_dancer.protocol`, and `model_calls_forbidden` from
`face_dancer.membrane`. `rider → protocol`/`membrane`; no cycles.

## The matcher (`rider/matcher.py`)

```python
from face_dancer.membrane import model_calls_forbidden
from face_dancer.protocol import Claim, ClaimEffect, Contest, Delta, ProposeDelta
from face_dancer.rider.rider import Clause, Rider


def matches(delta: Delta, rider: Rider) -> list[Clause]:
    """Every clause whose trigger fires on this delta (op + tag-set comparison).

    A clause fires when all its trigger tags are present on the delta and its op
    matches (an unset trigger op is a wildcard). Pure; returns mechanical and
    judgment clauses alike, in rider-list order.
    """
    return [
        clause
        for clause in rider.clauses
        if clause.trigger.tags <= delta.tags
        and (clause.trigger.op is None or clause.trigger.op == delta.op)
    ]


def _to_claim(clause: Clause) -> Claim:
    effect = (
        ClaimEffect(op=clause.effect.op, payload=clause.effect.payload)
        if clause.effect is not None
        else None
    )
    return Claim(claim=clause.claim, effect=effect)


def auto_contest(propose: ProposeDelta, rider: Rider) -> Contest | None:
    """Contest the mechanical clauses that fire on a propose_delta, in code.

    Returns a Contest carrying the fired mechanical clauses' claims (sharing the
    propose's correlation_id), or None if none fire. Runs in a model-free region:
    auto-contest never invokes the model.
    """
    with model_calls_forbidden("mechanical auto-contest is code-only"):
        fired = [c for c in matches(propose.delta, rider) if c.kind == "mechanical"]
        if not fired:
            return None
        return Contest(
            correlation_id=propose.correlation_id,
            claims=[_to_claim(c) for c in fired],
        )
```

Re-exported from `rider/__init__.py` (keep the docstring + the existing
`Clause`/`Rider`/`RiderEffect`/`Trigger` exports): `matches`, `auto_contest`.

## Testing

`tests/test_rider/test_matcher.py`:

1. **AC1 — mechanical fire-reduction, no model call:** a `propose_delta` with
   `delta.tags = {"fire"}` against a rider with a `mechanical` clause whose trigger
   is `tags={"fire"}` (op wildcard) and a `RiderEffect(SCALE, {"factor": 0.5})`:
   within `recorded_model_calls()`, `auto_contest` returns a `Contest` whose single
   `Claim` carries that clause's prose **and** a `ClaimEffect(SCALE, …)`, with the
   recorder **empty** and the contest's `correlation_id` equal to the propose's.
2. **AC8 — claim-only surfaces as prose:** a mechanical clause with no `effect`
   yields a `Claim` with `effect is None`.
3. **op wildcard vs specific:** a clause with `trigger.op = None` fires on any op;
   a clause with `trigger.op = REDUCE` fires only when `delta.op == REDUCE`.
4. **Tag-subset semantics:** a clause needing `{"fire", "magic"}` does **not** fire
   on a delta tagged only `{"fire"}`; it fires when both are present.
5. **Judgment excluded from the contest but matched:** a matching `judgment` clause
   is absent from `auto_contest`'s `Contest` (a contest of one mechanical clause),
   yet `matches(delta, rider)` includes it.
6. **No match → None:** `auto_contest` returns `None` when nothing fires (and when
   only judgment clauses fire).
7. **`matches` is pure / order:** returns the firing clauses in rider-list order.
8. **Public API:** `face_dancer.rider` re-exports `matches`, `auto_contest`.

`tests/test_rider/__init__.py` already exists. All code passes `mypy --strict` and
the existing ruff config.

## Out of scope

- **Judgment-clause routing to a mind** (#25) — `matches` exposes them; this issue
  does not route them.
- **`order`-proposal sequencing** of claims — the resolution loop's concern.
- The **session's adjudication** of the emitted contest, and the
  `request_roll`/`roll_result` resolution of a `grant_save`-style effect.
- The **resolution loop** (#26) that calls the matcher when a `propose_delta`
  arrives.
