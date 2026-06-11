"""The protocol's closed effect-op set and starter tag vocabulary.

Two shared vocabularies the delta schemas and the rider matcher draw on:

- ``EffectOp`` is **closed and versioned** — the mechanical verbs every host's
  executor must understand. Adding a member changes the wire contract and is a
  ``SCHEMA_VERSION`` bump (see ``version.py``). Pressure to add a conditional
  *inside* an op is the signal that the clause is a ``judgment`` rider clause,
  not a richer op — the set stays closed.
- The **tag vocabulary is open**: a delta's ``tags`` field stays
  ``frozenset[str]`` on the wire. The constants below are a documented v0 starter
  set seeded from canonical D&D 5e, for authoring, tests, and rider matching —
  NOT a wire constraint. A non-5e host brings its own tags with no protocol
  change.
"""

from enum import StrEnum


class EffectOp(StrEnum):
    """The closed, versioned set of effect operations a delta may carry."""

    REDUCE = "reduce"  # subtract from a resource (e.g. HP)
    SCALE = "scale"  # multiply a magnitude (resistance ½, vulnerability ×2)
    NEGATE = "negate"  # cancel the effect entirely (immunity)
    GRANT_SAVE = "grant_save"  # offer a saving throw not otherwise present
    MODIFY_ROLL = "modify_roll"  # adjust a roll (advantage, flat bonus)
    REPLACE = "replace"  # substitute one effect for another


# Starter tag vocabulary (v0), seeded from canonical D&D 5e. Documented guidance,
# not a wire constraint — the wire type for a delta's ``tags`` stays
# ``frozenset[str]``.

DAMAGE_TYPES: frozenset[str] = frozenset(
    {
        "acid",
        "bludgeoning",
        "cold",
        "fire",
        "force",
        "lightning",
        "necrotic",
        "piercing",
        "poison",
        "psychic",
        "radiant",
        "slashing",
        "thunder",
    }
)

CONDITIONS: frozenset[str] = frozenset(
    {
        "blinded",
        "charmed",
        "deafened",
        "exhaustion",
        "frightened",
        "grappled",
        "incapacitated",
        "invisible",
        "paralyzed",
        "petrified",
        "poisoned",
        "prone",
        "restrained",
        "stunned",
        "unconscious",
    }
)

STARTER_TAGS: frozenset[str] = DAMAGE_TYPES | CONDITIONS
