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
