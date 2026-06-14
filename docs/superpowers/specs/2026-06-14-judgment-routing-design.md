# Judgment-Clause Routing to a Mind

**Issue:** [#25](https://github.com/GeorgeLautenschlager/face-dancer/issues/25)
**Spike resolved:** [#5](https://github.com/GeorgeLautenschlager/face-dancer/issues/5)
**Date:** 2026-06-14
**Status:** Approved

## Purpose

Brief §5 — rider clauses tagged **`judgment`** route their one question to a mind
rather than auto-contesting in code. This keeps the closed op vocabulary closed: a
clause that wants a conditional is a `judgment` clause, not a richer op. Where
`auto_contest` (#23) settles `mechanical` clauses in code, this issue settles
`judgment` clauses through the model — the model-driven twin of the same matcher.

## The #5 spike, resolved

**When a `judgment` clause matches, the character's own model answers its one
question, reached through the injected `ModelGateway`.** The gateway *is* the
mind — the same seam `DecisionPolicy.choose_expressive` already uses for the
expressive path. "Punt the question to the host" becomes a later `ModelGateway`
*adapter*, not a v0 branch, so #25 needs **no** host-capability detection now. This
matches the self-owning-character thesis (the character brings its own mechanical
self-knowledge rather than trusting an arbitrary host to adjudicate). The routing
target is therefore an abstract `ModelGateway`; *which* mind it wraps (own model
now, host later) is the adapter's concern, deferred.

## Decisions

- **`route_judgment(propose, rider, gateway) -> Contest | None` is the judgment
  twin of `auto_contest`.** It reuses `matches(propose.delta, rider)` (#23) and
  keeps the `kind == "judgment"` clauses. For each, it routes one question to the
  mind and, for the clauses the mind affirms, surfaces a `Claim` — returning a
  `Contest` that shares the propose's `correlation_id`, or `None` when nothing
  fires or the mind affirms nothing. The output type is identical to
  `auto_contest`'s, so the resolution loop (#26) consumes mechanical and judgment
  contests uniformly.

- **The router is structurally model-*driven* (the DoD).** `auto_contest` runs
  inside `model_calls_forbidden`; `route_judgment` is its inverse — it **must**
  invoke the gateway for each judgment clause. "A matched judgment clause produces
  a routed question, **never a code verdict**" is a property of the path: code
  never decides whether the conditional holds; it only formulates the question and
  packages the clause the mind affirmed. Tests assert one `ModelCall` is recorded
  per judgment clause routed.

- **The mind judges applicability only; code authors the claim (model proposes,
  code disposes).** The gateway is handed a `JudgmentQuestion` and returns a
  `JudgmentAnswer(applies: bool, rationale: str | None)`. On `applies`, the router
  surfaces `_to_claim(clause)` — the **same** clause→`Claim` mapping `auto_contest`
  uses (imported from `rider.matcher`, reused for DRY). The model never authors the
  mechanic; it only judges whether the character's known rule applies. A wrong
  gateway return type raises `TypeError`, mirroring `choose_expressive`'s
  `isinstance` guard.

- **The question is the clause's prose plus the proposed change as context.**
  `JudgmentQuestion(claim: str, delta: Delta)` carries the clause's `claim` (the
  single question) and the `propose_delta`'s `delta` (what the character is
  reacting to). Both `JudgmentQuestion` and `JudgmentAnswer` are frozen dataclasses,
  matching `ExpressiveRequest`'s "adapter-owned request" shape — not pydantic wire
  models (they never cross the wire; they cross the membrane to the mind).

- **No new wire message; `SCHEMA_VERSION` unchanged.** The router emits an existing
  `Contest`; `JudgmentQuestion`/`JudgmentAnswer` are in-process types between the
  rider and the mind. No protocol or schema change.

## Architecture

A new leaf module in the existing `rider/` package, re-exported from its
`__init__.py`.

```
src/face_dancer/rider/
├── __init__.py     # re-export route_judgment, JudgmentQuestion, JudgmentAnswer (+ existing)
├── rider.py        # (existing) the schema
├── matcher.py      # (existing) matches(), auto_contest(), _to_claim()
└── judgment.py     # NEW: JudgmentQuestion, JudgmentAnswer, route_judgment()
```

Dependency direction: `judgment.py` imports `matches` and `_to_claim` from
`face_dancer.rider.matcher`, `Clause`/`Rider` from `face_dancer.rider.rider`,
`Contest`/`Delta`/`ProposeDelta` from `face_dancer.protocol`, and `ModelGateway`
from `face_dancer.membrane`. `rider → protocol`/`membrane`/`rider.matcher`; no
cycles (parallels `matcher.py`, which already depends on `protocol`/`membrane`).
Reuse of the module-private `_to_claim` is deliberate within-package DRY — it is
the canonical clause→`Claim` mapping shared by both the mechanical and judgment
paths.

## The router (`rider/judgment.py`)

```python
"""Judgment-clause routing: a judgment clause's one question goes to a mind."""

from dataclasses import dataclass

from face_dancer.membrane import ModelGateway
from face_dancer.protocol import Claim, Contest, Delta, ProposeDelta
from face_dancer.rider.matcher import _to_claim, matches
from face_dancer.rider.rider import Rider


@dataclass(frozen=True)
class JudgmentQuestion:
    """The single question a judgment clause raises, handed to the mind.

    ``claim`` is the clause's prose (the question); ``delta`` is the proposed
    change the character is reacting to (context). Crosses the membrane to the
    mind, not the wire — hence a dataclass, not a protocol model.
    """

    claim: str
    delta: Delta


@dataclass(frozen=True)
class JudgmentAnswer:
    """The mind's verdict on a judgment question: does the clause apply?

    Narrow by design — the mind judges applicability; code authors the surfaced
    claim from the clause. ``rationale`` is optional prose the mind may attach.
    """

    applies: bool
    rationale: str | None = None


def route_judgment(
    propose: ProposeDelta, rider: Rider, gateway: ModelGateway
) -> Contest | None:
    """Route each fired judgment clause's question to the mind; contest the affirmed.

    The model-driven twin of ``auto_contest``: it MUST invoke the gateway for each
    judgment clause (never a code verdict). Returns a Contest of the mind-affirmed
    clauses' claims (sharing the propose's correlation_id), or None when no
    judgment clause fires or the mind affirms none.
    """
    fired = [c for c in matches(propose.delta, rider) if c.kind == "judgment"]
    claims: list[Claim] = []
    for clause in fired:
        question = JudgmentQuestion(claim=clause.claim, delta=propose.delta)
        answer = gateway.invoke("rider.judgment", question)
        if not isinstance(answer, JudgmentAnswer):
            raise TypeError(
                f"judgment gateway returned {type(answer).__name__}, "
                "expected JudgmentAnswer"
            )
        if answer.applies:
            claims.append(_to_claim(clause))
    if not claims:
        return None
    return Contest(correlation_id=propose.correlation_id, claims=claims)
```

Re-exported from `rider/__init__.py` (keep the docstring; add to the sorted import
block and `__all__`): `route_judgment`, `JudgmentQuestion`, `JudgmentAnswer`.

## Testing

`tests/test_rider/test_judgment.py`, using a fake `ModelGateway` whose `_invoke`
returns a configurable `JudgmentAnswer` and records the `JudgmentQuestion`s it saw:

1. **Affirmed judgment clause → contest (the DoD path):** a judgment clause fires;
   the mind returns `applies=True`; `route_judgment` returns a `Contest` whose
   single `Claim` carries the clause's prose **and** its `ClaimEffect` (via
   `_to_claim`), with `correlation_id == propose.correlation_id`. The fake gateway
   recorded **one** call — the path is model-driven, not model-free.
2. **One ModelCall per judgment clause:** within `recorded_model_calls()`, routing
   N judgment clauses records N `ModelCall`s on path `"rider.judgment"`.
3. **Mind declines → clause omitted:** `applies=False` for the only fired clause →
   `route_judgment` returns `None`; the gateway was still invoked (question routed).
4. **Claim-only judgment clause:** an affirmed clause with no `effect` surfaces a
   `Claim` with `effect is None`.
5. **Mechanical clauses are never routed:** a rider with a matching `mechanical`
   clause and no judgment clause yields `None` and **no** gateway call (mechanical
   is `auto_contest`'s job).
6. **Mixed rider:** with one mechanical and one judgment clause both firing, only
   the judgment clause is routed and contested.
7. **No judgment match → None, no model call:** a delta that fires nothing (or only
   non-matching clauses) returns `None` and records zero calls.
8. **Wrong gateway return type → TypeError:** a gateway returning a non-
   `JudgmentAnswer` raises `TypeError`.
9. **The question carries the clause claim + delta:** assert the recorded
   `JudgmentQuestion.claim == clause.claim` and `.delta == propose.delta`.
10. **Public API:** `face_dancer.rider` re-exports `route_judgment`,
    `JudgmentQuestion`, `JudgmentAnswer`.

`tests/test_rider/__init__.py` already exists. All code passes `mypy --strict` and
the existing ruff config.

## Out of scope

- **Punt-to-host** routing and **host-capability detection** — a later
  `ModelGateway` adapter; the spike defers them (own model is the v0 mind).
- The **real `ModelGateway` adapter** (the character's actual model) — still a
  brief non-goal; #25 needs only the abstract gateway and a test double.
- The **resolution loop** (#26) that calls `route_judgment` when a `propose_delta`
  arrives and adjudicates the emitted `Contest`.
- **`order`-proposal sequencing** of the surfaced claims — the loop's concern.
- Any change to `auto_contest`, the matcher, or the wire protocol.
