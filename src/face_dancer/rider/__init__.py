"""Rules rider — reactive, character-known mechanics the host may not know.

Covers resistances, special saves, and homebrew clauses.
Clauses are tagged `mechanical` (auto-contest in code) or `judgment` (routed to a mind).
Rider triggers match on op + tag-set; the effect-op vocabulary is closed and versioned.
"""

from face_dancer.rider.judgment import JudgmentAnswer, JudgmentQuestion, route_judgment
from face_dancer.rider.matcher import auto_contest, matches
from face_dancer.rider.rider import Clause, Rider, RiderEffect, Trigger

__all__ = [
    "Clause",
    "JudgmentAnswer",
    "JudgmentQuestion",
    "Rider",
    "RiderEffect",
    "Trigger",
    "auto_contest",
    "matches",
    "route_judgment",
]
