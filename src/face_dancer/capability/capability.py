"""The Capability model: a proactive action the character knows it can attempt."""

from uuid import UUID

from pydantic import BaseModel

from face_dancer.protocol import Intent


class Capability(BaseModel):
    """A proactive capability the character knows it can attempt.

    ``name`` is the host-understood action reference (becomes ``Intent.action``);
    ``description`` is prose the decision step reads to choose; ``tags`` reuse the
    protocol tag vocabulary so a capability can correlate with rider/perception.
    A capability declares what the character *can* do — never what is legal now
    (affordance is session-owned), so it carries no availability field.
    """

    name: str
    description: str
    tags: frozenset[str] = frozenset()

    def to_intent(
        self,
        correlation_id: UUID,
        target: str | None = None,
        narration: str | None = None,
    ) -> Intent:
        """Build the character-side ``intent`` that proposes this capability."""
        return Intent(
            correlation_id=correlation_id,
            action=self.name,
            target=target,
            narration=narration,
        )
