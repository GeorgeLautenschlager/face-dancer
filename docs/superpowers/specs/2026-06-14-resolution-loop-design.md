# Resolution Loop Orchestration — One Spine, Two Directions

**Issue:** [#26](https://github.com/GeorgeLautenschlager/face-dancer/issues/26)
**Date:** 2026-06-14
**Status:** Approved

## Purpose

Brief §3/§5 — **one resolution loop, two directions.** World-acts-on-character and
character-acts-on-world resolve through the same spine
(`propose → contest? → request_roll? → apply`), so a self-caused action needs no
separate machinery. This issue is the keystone that wires the already-built
character-side steps — `auto_contest`/`route_judgment` (#23/#25), `roll` (#20),
`apply` (#19) — into one orchestrator, driven against a session that owns every
verdict.

## Decisions

- **A driver `ResolutionLoop`, not a per-message reducer.** The loop holds the
  character's bundle (`sheet`, `rider`, `state`, `gateway`, `rng`) and *drives* the
  exchange: it sequences contest → optional roll → apply, calling an injected
  `Session` for each session-owned verdict. This front-loads the orchestration here
  (what #26 is for); a host wires the `Session` to transport, #27's mock hosts
  implement it, and tests use doubles.

- **`Session` is a `Protocol` — the host-membrane seam.** The character calls it
  for each verdict it does not own:

  ```python
  class Session(Protocol):
      def adjudicate_intent(self, intent: Intent) -> ProposeDelta: ...
      def adjudicate_propose(
          self, propose: ProposeDelta, contest: Contest | None
      ) -> RequestRoll | ApplyDelta: ...
      def adjudicate_roll(self, result: RollResult) -> ApplyDelta: ...
  ```

  `adjudicate_propose` is called on *every* inbound exchange (with `contest=None`
  when nothing fires); it returns a `RequestRoll` to gate the change behind a roll,
  or the authoritative `ApplyDelta` to commit. This is "ownership ≠ authority": the
  character surfaces claims and rolls; the **session owns the final number**.

- **`resolve_outbound` reuses `resolve_inbound` verbatim — one spine, two
  directions.** An `intent` adjudicates (via `adjudicate_intent`) into a
  `propose_delta`, then follows the *identical* inbound path. Both directions
  converge on the single `apply` writer, returning `Applied[DynamicState]` — that
  convergence **is** AC10.

- **The contest merges both character paths.** `_contest(propose)` runs
  `auto_contest` (mechanical, model-free) **and** `route_judgment` (judgment,
  model-driven through the gateway), concatenating their claims into one `Contest`
  sharing `propose.correlation_id`, or `None` when neither fires. The session sees
  a single contest carrying every surfaced claim.

- **The spine is linear and acyclic: one contest, at most one roll, one apply**
  (the #4 decision). `adjudicate_propose` may return a single `RequestRoll`; the
  loop rolls once, hands the `roll_result` to `adjudicate_roll`, and applies the
  `ApplyDelta` it returns. No loop-back, no second contest.

- **One runtime guard: the terminal apply carries this exchange's
  `correlation_id`.** Before committing, the loop raises `ResolutionError` if
  `apply_delta.correlation_id != propose.correlation_id` — making "correlation_id
  carries causality" (the #4 decision) structural: the committed write must belong
  to the exchange it resolves. The `Session` Protocol's precise return types are
  the type contract (a conforming host returns the right message type, checked by
  *its* mypy), so the loop adds **no** redundant `isinstance` type-guards — it
  guards causality (a value), not types (already the contract). `apply` may still
  raise `ApplyError`, which propagates unchanged.

## Architecture

A new leaf module in the existing `resolution/` package, re-exported from its
`__init__.py`.

```
src/face_dancer/resolution/
├── __init__.py     # re-export ResolutionLoop, Session, ResolutionError (+ existing)
├── apply.py        # (existing) apply(), ApplyError
├── roll.py         # (existing) roll()
└── loop.py         # NEW: Session, ResolutionError, ResolutionLoop
```

Dependency direction: `loop.py` imports `apply`/`ApplyError` and `roll` from
`face_dancer.resolution`, `auto_contest`/`route_judgment`/`Rider` from
`face_dancer.rider`, the messages from `face_dancer.protocol`, `Applied`/
`ModelGateway` from `face_dancer.membrane`, `Sheet` from `face_dancer.sheet`, and
`DynamicState` from `face_dancer.state`. The loop sits *above* the other
resolution modules — it composes them; no cycles.

## The loop (`resolution/loop.py`)

```python
"""The resolution loop: one spine (propose -> contest? -> roll? -> apply), two directions."""

import random
from typing import Protocol

from face_dancer.membrane import Applied, ModelGateway
from face_dancer.protocol import (
    ApplyDelta,
    Contest,
    Intent,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.resolution.apply import apply
from face_dancer.resolution.roll import roll
from face_dancer.rider import Rider, auto_contest, route_judgment
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState


class ResolutionError(Exception):
    """A resolved exchange violated the spine — e.g. a committed apply_delta whose
    correlation_id does not match the propose_delta it claims to finalize."""


class Session(Protocol):
    """The session's adjudication seam: every verdict the character does not own.

    A real host wires these to transport; #27's mock hosts implement them. The
    character surfaces claims and rolls; the session owns the final number.
    """

    def adjudicate_intent(self, intent: Intent) -> ProposeDelta: ...

    def adjudicate_propose(
        self, propose: ProposeDelta, contest: Contest | None
    ) -> RequestRoll | ApplyDelta: ...

    def adjudicate_roll(self, result: RollResult) -> ApplyDelta: ...


class ResolutionLoop:
    """Drive a character bundle's resolution: contest -> roll? -> apply, both ways."""

    def __init__(
        self,
        *,
        sheet: Sheet,
        rider: Rider,
        state: DynamicState,
        gateway: ModelGateway,
        rng: random.Random | None = None,
    ) -> None:
        self.sheet = sheet
        self.rider = rider
        self.state = state
        self.gateway = gateway
        self.rng = rng

    def _contest(self, propose: ProposeDelta) -> Contest | None:
        """Merge the mechanical and judgment contests into one (or None)."""
        mechanical = auto_contest(propose, self.rider)
        judgment = route_judgment(propose, self.rider, self.gateway)
        claims = (mechanical.claims if mechanical else []) + (
            judgment.claims if judgment else []
        )
        if not claims:
            return None
        return Contest(correlation_id=propose.correlation_id, claims=claims)

    def resolve_inbound(
        self, propose: ProposeDelta, session: Session
    ) -> Applied[DynamicState]:
        """World-acts-on-character: propose -> contest? -> roll? -> apply."""
        contest = self._contest(propose)
        decision = session.adjudicate_propose(propose, contest)
        if isinstance(decision, RequestRoll):
            result = roll(decision, self.sheet, self.rider, rng=self.rng)
            final = session.adjudicate_roll(result)
        else:
            final = decision
        if final.correlation_id != propose.correlation_id:
            raise ResolutionError(
                f"apply_delta correlation_id {final.correlation_id} does not match "
                f"propose_delta {propose.correlation_id}"
            )
        return apply(final, self.state)

    def resolve_outbound(
        self, intent: Intent, session: Session
    ) -> Applied[DynamicState]:
        """Character-acts-on-world: intent -> (session) propose -> the inbound path."""
        propose = session.adjudicate_intent(intent)
        return self.resolve_inbound(propose, session)
```

Re-exported from `resolution/__init__.py` (keep the docstring; add to the sorted
import block and `__all__`): `ResolutionLoop`, `Session`, `ResolutionError`.

## Testing

`tests/test_resolution/test_loop.py`, using small `Session` doubles (a recording
double that returns scripted messages and captures what it was handed):

1. **AC10 inbound (world-caused):** an incoming `propose_delta` that reduces HP; a
   double whose `adjudicate_propose` returns the committing `ApplyDelta` (reduce
   `hp`). `resolve_inbound` returns an `Applied[DynamicState]` and `loop.state.hp`
   dropped by the amount.
2. **AC10 outbound (self-caused):** an `intent` ("use an item"); a double whose
   `adjudicate_intent` returns a `propose_delta` (reduce a `resources` key) and
   `adjudicate_propose` returns the `ApplyDelta`. `resolve_outbound` returns an
   `Applied` and the resource dropped — **the same `apply` path** as inbound.
3. **Contest surfaced to the session:** a `propose` tagged to fire a mechanical
   rider clause; the recording double captures a non-`None` `Contest` whose claim
   carries the clause's prose (so the session got the character's surfaced rule).
4. **Judgment path threads the gateway:** a `propose` firing a `judgment` clause
   routes through the gateway (a stub mind returning `applies=True`); the merged
   contest the session receives includes the judgment claim.
5. **Merged contest:** a rider with both a mechanical and a judgment clause firing
   yields a single contest carrying **both** claims.
6. **Roll path threaded:** `adjudicate_propose` returns a `RequestRoll`; the loop
   rolls (seeded `rng`, so the `roll_result` is deterministic), hands it to
   `adjudicate_roll` (the double captures the `RollResult` and returns the
   `ApplyDelta`), and applies it. Assert the captured result's `total` and the
   state change.
7. **Uncontested:** an empty rider → `adjudicate_propose` is called with
   `contest=None`.
8. **Correlation guard:** an `ApplyDelta` whose `correlation_id` differs from the
   propose's raises `ResolutionError`; the matching case does not.
9. **`ApplyError` propagates:** a committing `ApplyDelta` with a non-terminal op
   (e.g. `scale`) raises `ApplyError` out of the loop.
10. **The apply step is model-free:** wrapping `resolve_inbound` (uncontested,
    empty rider so no judgment routing) in `recorded_model_calls()` records no
    calls; and the commit goes through `dispose` (an `Applied` is returned).
11. **Public API:** `face_dancer.resolution` re-exports `ResolutionLoop`,
    `Session`, `ResolutionError`.

`tests/test_resolution/__init__.py` already exists. All code passes `mypy --strict`
and the existing ruff config.

## Out of scope

- **The real adjudicating session / host** — `Session` is a Protocol; #27's mock
  hosts implement it. No reference session ships here (host adjudication policy is
  the host's, not the character package's).
- **Multi-roll or multi-contest exchanges, loop-back** — the spine is linear and
  acyclic (one contest, one roll, one apply) per #4.
- **Context-conditioned rider roll modifiers** ("vs poison") — deferred with the
  roll engine (#20); the loop passes the rider to `roll` as-is.
- **Transport / async message routing** — the `Session` port abstracts it; the
  real wiring is the host adapter's concern.
- The **real `ModelGateway` adapter** — still a brief non-goal; tests use a double.
