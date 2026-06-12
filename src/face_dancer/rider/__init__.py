"""Rules rider — reactive, character-known mechanics the host may not know.

Covers resistances, special saves, and homebrew clauses.
Clauses are tagged `mechanical` (auto-contest in code) or `judgment` (routed to a mind).
Rider triggers match on op + tag-set; the effect-op vocabulary is closed and versioned.
"""

from face_dancer.rider.rider import Clause, Rider, RiderEffect, Trigger

__all__ = ["Clause", "Rider", "RiderEffect", "Trigger"]
