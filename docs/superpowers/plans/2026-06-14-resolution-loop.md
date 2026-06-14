# Resolution Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ResolutionLoop` — one spine (`propose → contest? → roll? → apply`) that resolves both a world-caused `propose_delta` (inbound) and a self-caused `intent` (outbound) to a committed state change, driven against an injected `Session` adjudication port.

**Architecture:** One new leaf module `resolution/loop.py` with a `Session` Protocol (the host-membrane seam), a `ResolutionError`, and the `ResolutionLoop` class that composes the existing `auto_contest`/`route_judgment`/`roll`/`apply`. Re-exported from `resolution/__init__.py`. One task — the module is one cohesive orchestrator.

**Tech Stack:** Python 3.11+, pydantic v2 (consumed models), `random` + `typing.Protocol` (stdlib), pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-14-resolution-loop-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's changes. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **199 passed**.

Reference shapes (already on this base):
- `apply(message: ApplyDelta, state: DynamicState) -> Applied[DynamicState]` and `ApplyError`, both in `face_dancer.resolution`.
- `roll(request: RequestRoll, sheet: Sheet, rider: Rider, *, rng=None) -> RollResult`.
- `auto_contest(propose: ProposeDelta, rider: Rider) -> Contest | None` and `route_judgment(propose, rider, gateway) -> Contest | None`, both in `face_dancer.rider`.
- `Contest.claims: list[Claim]`; `DynamicState(hp, conditions, resources, position)`; `Applied[T].result` is the `T`.
- `random.Random(0).randint(1, 20) == 13` (the pinned deterministic natural roll).

---

## Task 1: The resolution loop (`resolution/loop.py`)

**Files:**
- Create: `src/face_dancer/resolution/loop.py`
- Modify: `src/face_dancer/resolution/__init__.py`
- Test: `tests/test_resolution/test_loop.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resolution/test_loop.py`:

```python
"""Tests for the resolution loop: one spine (propose -> contest? -> roll? -> apply)."""

import random
from uuid import UUID, uuid4

import pytest

from face_dancer.membrane import ModelGateway, recorded_model_calls
from face_dancer.protocol import (
    ApplyDelta,
    Contest,
    Delta,
    EffectOp,
    Intent,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.resolution import ResolutionError, ResolutionLoop
from face_dancer.resolution.apply import ApplyError
from face_dancer.rider import Clause, JudgmentAnswer, Rider, RiderEffect, Trigger
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState


class _AffirmingMind(ModelGateway):
    """A stub mind that affirms every judgment question (for route_judgment)."""

    def _invoke(self, request: object) -> object:
        return JudgmentAnswer(applies=True)


class _Session:
    """A scripted, recording Session double.

    ``propose_for_intent`` is returned by adjudicate_intent; ``decision`` by
    adjudicate_propose; ``apply_for_roll`` by adjudicate_roll. It records the
    contest and roll it was handed.
    """

    def __init__(
        self,
        *,
        decision: RequestRoll | ApplyDelta | None = None,
        propose_for_intent: ProposeDelta | None = None,
        apply_for_roll: ApplyDelta | None = None,
    ) -> None:
        self._decision = decision
        self._propose_for_intent = propose_for_intent
        self._apply_for_roll = apply_for_roll
        self.seen_contest: Contest | None = None
        self.seen_contest_set = False
        self.seen_roll: RollResult | None = None

    def adjudicate_intent(self, intent: Intent) -> ProposeDelta:
        assert self._propose_for_intent is not None
        return self._propose_for_intent

    def adjudicate_propose(
        self, propose: ProposeDelta, contest: Contest | None
    ) -> RequestRoll | ApplyDelta:
        self.seen_contest = contest
        self.seen_contest_set = True
        assert self._decision is not None
        return self._decision

    def adjudicate_roll(self, result: RollResult) -> ApplyDelta:
        self.seen_roll = result
        assert self._apply_for_roll is not None
        return self._apply_for_roll


def _loop(
    *,
    rider: Rider | None = None,
    state: DynamicState | None = None,
    sheet: Sheet | None = None,
    gateway: ModelGateway | None = None,
    seed: int = 0,
) -> ResolutionLoop:
    return ResolutionLoop(
        sheet=sheet if sheet is not None else Sheet(),
        rider=rider if rider is not None else Rider(),
        state=state if state is not None else DynamicState(hp=20),
        gateway=gateway if gateway is not None else _AffirmingMind(),
        rng=random.Random(seed),
    )


def _propose(cid: UUID, *, target: str = "hp", amount: int = 5, tags: set[str] | None = None) -> ProposeDelta:
    return ProposeDelta(
        correlation_id=cid,
        delta=Delta(
            op=EffectOp.REDUCE,
            tags=frozenset(tags or set()),
            payload={"target": target, "amount": amount},
        ),
    )


def _apply_delta(cid: UUID, *, target: str = "hp", amount: int = 5) -> ApplyDelta:
    return ApplyDelta(
        correlation_id=cid,
        delta=Delta(op=EffectOp.REDUCE, tags=frozenset(), payload={"target": target, "amount": amount}),
    )


def _judgment_clause(*, claim: str, tags: set[str]) -> Clause:
    return Clause(claim=claim, trigger=Trigger(tags=frozenset(tags)), kind="judgment", source="t")


def _mechanical_clause(*, claim: str, tags: set[str], effect: RiderEffect | None = None) -> Clause:
    return Clause(
        claim=claim, trigger=Trigger(tags=frozenset(tags)), kind="mechanical", source="t", effect=effect
    )


# --- AC10: both directions reach apply ---


def test_ac10_inbound_world_caused_reaches_apply() -> None:
    cid = uuid4()
    loop = _loop(state=DynamicState(hp=20))
    session = _Session(decision=_apply_delta(cid, target="hp", amount=5))
    applied = loop.resolve_inbound(_propose(cid, target="hp", amount=5), session)
    assert loop.state.hp == 15
    assert applied.result.hp == 15
    assert applied.result is loop.state


def test_ac10_outbound_self_caused_reaches_apply_same_path() -> None:
    cid = uuid4()
    loop = _loop(state=DynamicState(hp=20, resources={"potion": 3}))
    propose = ProposeDelta(
        correlation_id=cid,
        delta=Delta(op=EffectOp.REDUCE, tags=frozenset(), payload={"target": "resources", "key": "potion", "amount": 1}),
    )
    session = _Session(
        propose_for_intent=propose,
        decision=ApplyDelta(correlation_id=cid, delta=propose.delta),
    )
    applied = loop.resolve_outbound(Intent(correlation_id=cid, action="use_item", target="potion"), session)
    assert loop.state.resources["potion"] == 2
    assert applied.result.resources["potion"] == 2


# --- contest surfacing ---


def test_mechanical_contest_is_surfaced_to_the_session() -> None:
    cid = uuid4()
    rider = Rider(clauses=[_mechanical_clause(claim="I resist fire", tags={"fire"})])
    loop = _loop(rider=rider)
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert session.seen_contest is not None
    assert [c.claim for c in session.seen_contest.claims] == ["I resist fire"]


def test_judgment_contest_threads_the_gateway() -> None:
    cid = uuid4()
    rider = Rider(clauses=[_judgment_clause(claim="argue for a save", tags={"fire"})])
    loop = _loop(rider=rider)
    session = _Session(decision=_apply_delta(cid))
    with recorded_model_calls() as rec:
        loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert [c.path for c in rec.calls] == ["rider.judgment"]
    assert session.seen_contest is not None
    assert [c.claim for c in session.seen_contest.claims] == ["argue for a save"]


def test_merged_contest_carries_mechanical_and_judgment_claims() -> None:
    cid = uuid4()
    rider = Rider(
        clauses=[
            _mechanical_clause(claim="resist", tags={"fire"}),
            _judgment_clause(claim="argue", tags={"fire"}),
        ]
    )
    loop = _loop(rider=rider)
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert session.seen_contest is not None
    assert {c.claim for c in session.seen_contest.claims} == {"resist", "argue"}


def test_uncontested_calls_adjudicate_propose_with_none() -> None:
    cid = uuid4()
    loop = _loop(rider=Rider())  # empty rider: nothing fires
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid, tags={"fire"}), session)
    assert session.seen_contest_set
    assert session.seen_contest is None


# --- roll path ---


def test_roll_path_is_threaded_and_applied() -> None:
    cid = uuid4()
    # sheet gives +3 on the kind; seed 0 -> natural 13 -> total 16
    loop = _loop(
        state=DynamicState(hp=20),
        sheet=Sheet(modifiers={"dexterity_save": 3}),
        seed=0,
    )
    session = _Session(
        decision=RequestRoll(correlation_id=cid, kind="dexterity_save", dc=15),
        apply_for_roll=_apply_delta(cid, target="hp", amount=4),
    )
    loop.resolve_inbound(_propose(cid), session)
    assert session.seen_roll is not None
    assert session.seen_roll.natural == 13
    assert session.seen_roll.total == 16
    assert loop.state.hp == 16  # 20 - 4


# --- guards ---


def test_correlation_mismatch_raises_resolution_error() -> None:
    cid = uuid4()
    loop = _loop()
    session = _Session(decision=_apply_delta(uuid4()))  # wrong correlation_id
    with pytest.raises(ResolutionError):
        loop.resolve_inbound(_propose(cid), session)


def test_matching_correlation_does_not_raise() -> None:
    cid = uuid4()
    loop = _loop(state=DynamicState(hp=20))
    session = _Session(decision=_apply_delta(cid))
    loop.resolve_inbound(_propose(cid), session)  # no raise
    assert loop.state.hp == 15


def test_apply_error_propagates() -> None:
    cid = uuid4()
    loop = _loop()
    bad = ApplyDelta(correlation_id=cid, delta=Delta(op=EffectOp.SCALE, tags=frozenset(), payload={}))
    session = _Session(decision=bad)
    with pytest.raises(ApplyError):
        loop.resolve_inbound(_propose(cid), session)


# --- model-free apply ---


def test_uncontested_resolution_makes_no_model_call() -> None:
    cid = uuid4()
    loop = _loop(rider=Rider(), state=DynamicState(hp=20))  # empty rider: no judgment routing
    session = _Session(decision=_apply_delta(cid))
    with recorded_model_calls() as rec:
        loop.resolve_inbound(_propose(cid), session)
    assert rec.calls == []


# --- public API ---


def test_public_api_is_reexported() -> None:
    import face_dancer.resolution as resolution

    assert hasattr(resolution, "ResolutionLoop")
    assert hasattr(resolution, "Session")
    assert hasattr(resolution, "ResolutionError")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution/test_loop.py -v`
Expected: FAIL — `ImportError: cannot import name 'ResolutionLoop' from 'face_dancer.resolution'`.

- [ ] **Step 3: Write the loop module**

Create `src/face_dancer/resolution/loop.py`:

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
        claims = (mechanical.claims if mechanical else []) + (judgment.claims if judgment else [])
        if not claims:
            return None
        return Contest(correlation_id=propose.correlation_id, claims=claims)

    def resolve_inbound(self, propose: ProposeDelta, session: Session) -> Applied[DynamicState]:
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

    def resolve_outbound(self, intent: Intent, session: Session) -> Applied[DynamicState]:
        """Character-acts-on-world: intent -> (session) propose -> the inbound path."""
        propose = session.adjudicate_intent(intent)
        return self.resolve_inbound(propose, session)
```

- [ ] **Step 4: Re-export from the resolution package**

Edit `src/face_dancer/resolution/__init__.py` — KEEP the existing module docstring.
The import block and `__all__` become (imports sorted: `apply` before `loop` before
`roll`; `__all__` kept alphabetical):

```python
from face_dancer.resolution.apply import ApplyError, apply
from face_dancer.resolution.loop import ResolutionError, ResolutionLoop, Session
from face_dancer.resolution.roll import roll

__all__ = [
    "ApplyError",
    "ResolutionError",
    "ResolutionLoop",
    "Session",
    "apply",
    "roll",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_resolution/test_loop.py -v`
Expected: PASS (12 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/resolution/loop.py src/face_dancer/resolution/__init__.py tests/test_resolution/test_loop.py
git commit -m "feat(resolution): add the resolution loop orchestrator (issue #26)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~211 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
import random
from uuid import uuid4
from face_dancer.membrane import NullModelGateway
from face_dancer.protocol import ApplyDelta, Delta, EffectOp, Intent, ProposeDelta
from face_dancer.resolution import ResolutionLoop
from face_dancer.rider import Rider
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState

class Sess:
    def __init__(self, cid): self.cid = cid
    def adjudicate_intent(self, intent):
        return ProposeDelta(correlation_id=self.cid, delta=Delta(op=EffectOp.REDUCE, tags=frozenset(), payload={'target':'hp','amount':3}))
    def adjudicate_propose(self, propose, contest):
        return ApplyDelta(correlation_id=self.cid, delta=propose.delta)
    def adjudicate_roll(self, result):
        return ApplyDelta(correlation_id=self.cid, delta=Delta(op=EffectOp.REDUCE, tags=frozenset(), payload={'target':'hp','amount':result.total}))

cid = uuid4()
loop = ResolutionLoop(sheet=Sheet(), rider=Rider(), state=DynamicState(hp=20), gateway=NullModelGateway(), rng=random.Random(0))
loop.resolve_outbound(Intent(correlation_id=cid, action='brace'), Sess(cid))
print('outbound hp:', loop.state.hp)   # 17
"
# outbound hp: 17
```

## Out of scope (do NOT implement)

- The **real adjudicating session / host** — `Session` is a Protocol; #27's mock
  hosts implement it. No reference session ships here.
- **Multi-roll / multi-contest / loop-back** — the spine is linear and acyclic.
- **Context-conditioned rider roll modifiers** ("vs poison") — deferred with #20.
- **Transport / async routing** — the `Session` port abstracts it.
- Any change to `apply`, `roll`, `auto_contest`, `route_judgment`, or the protocol.
