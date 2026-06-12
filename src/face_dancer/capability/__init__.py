"""Capability interface — the character's proactive 'what I can do'.

Capabilities are character-known and feed intent generation; affordance (what is
legal now) is session-owned, so the character proposes and never enumerates its
own legal moves.
"""

from face_dancer.capability.capability import Capability

__all__ = ["Capability"]
