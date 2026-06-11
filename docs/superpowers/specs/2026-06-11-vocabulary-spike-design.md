# Spike: Starter Tag Vocabulary + Closed Effect-Op Initial Members

**Issue:** [#3](https://github.com/GeorgeLautenschlager/face-dancer/issues/3)
**Date:** 2026-06-11
**Status:** Approved

## Purpose

A time-boxed, decision-producing spike (brief §7 open question). It answers two
questions that block the delta schemas ([#11](https://github.com/GeorgeLautenschlager/face-dancer/issues/11))
and the rider matcher:

1. What are the exact initial members of the **closed effect-op set**?
2. What is the starter **tag vocabulary** (damage types, condition names) for v0?

The effect-op set is closed and versioned — adding an op is a schema-version
bump. The tag vocabulary is the shared set the rider matcher compares against
(op + tag-set). Both need concrete starter members before the delta schemas, the
effect-op-typed `op` field, and the rider matcher can be built.

This spike produces a small `vocabulary.py` module in the protocol package (plus
tests) that codifies the decisions so #11 and the rider can import them. It makes
**no** message or wire-schema changes — those belong to #11. The deliverables:

1. A closed `EffectOp` enum with exactly the brief §5 members.
2. A documented starter tag vocabulary exported as constants, seeded from D&D 5e.
3. This decision record.

## Decisions

- **Effect-ops are a closed `StrEnum`, exactly the brief §5 set** — `reduce`,
  `scale`, `negate`, `grant_save`, `modify_roll`, `replace`. `StrEnum` (Python
  3.11+) rather than a bare `Literal` because the rider and the (future) executor
  reference and iterate members (`EffectOp.REDUCE`), and it serializes to its
  string value on the wire. A `Literal` would give validation but no member
  handles to share across subsystems. Membership is taken verbatim from the brief,
  which already pinned these six; this spike does not add or remove any.

- **Adding an `EffectOp` member is a protocol `SCHEMA_VERSION` bump** — the op
  vocabulary is part of the closed, versioned wire contract (brief §5: "A new op
  is a schema-version bump"). This is documented in `vocabulary.py` and
  cross-referenced to `version.py`, the one defined change point. Pressure to add
  a *conditional* inside an op is the signal that the clause is a `judgment` rider
  clause, not a richer op — the op set stays closed (brief §6 rejected
  alternative).

- **Tags are open strings with a documented starter vocabulary, not a closed
  enum** — the wire type stays `frozenset[str]`; the protocol *exports* a v0
  starter set as `frozenset[str]` constants for guidance, tests, and rider
  matching, but does not constrain the wire to them. Rationale: the brief's
  structure is system-agnostic — "a 5e character is portable into any other 5e
  game, and the same is true of any ruleset." A closed tag enum would bake one
  rule system into the protocol and force a schema-version bump for every new
  host's tags; a space-sim host (Feudal Carriers) brings its own tags with no
  protocol change. Closing the *ops* (the mechanical verbs every host's executor
  must understand) while leaving *tags* open (the system-specific nouns) puts the
  closed/open line exactly where portability needs it.

- **Starter tags are seeded from canonical D&D 5e** — the full 13 damage types
  and 15 conditions, not a trimmed subset. 5e is the brief's worked example and
  the Deathwatch host's system; the full canonical lists are well-defined and
  cost nothing extra to enumerate. Because tags are open strings, this set is
  documented guidance, not a constraint — so completeness is free and a non-5e
  host simply ignores it.

## Architecture

A new leaf module under the existing protocol package:

```
src/face_dancer/protocol/
├── ...
└── vocabulary.py    # EffectOp (closed enum) + starter tag constants
```

`vocabulary.py` imports nothing from the rest of the package (it is a pure leaf;
`version.py`-style). `protocol/__init__.py` re-exports the new public names. #11
will import `EffectOp` for the delta `op` field; the rider will import the tag
constants for its matcher.

## The vocabulary (`vocabulary.py`)

```python
from enum import StrEnum


class EffectOp(StrEnum):
    """The closed, versioned set of effect operations a delta may carry.

    Adding a member changes the wire contract and is a SCHEMA_VERSION bump
    (see version.py). Reactive rider clauses match on op + tag-set.
    """

    REDUCE = "reduce"          # subtract from a resource (e.g. HP)
    SCALE = "scale"            # multiply a magnitude (resistance ½, vulnerability ×2)
    NEGATE = "negate"          # cancel the effect entirely (immunity)
    GRANT_SAVE = "grant_save"  # offer a saving throw that wasn't otherwise present
    MODIFY_ROLL = "modify_roll"  # adjust a roll (advantage, flat bonus)
    REPLACE = "replace"        # substitute one effect for another


# Starter tag vocabulary (v0), seeded from canonical D&D 5e. The wire type for a
# delta's `tags` stays `frozenset[str]`; these constants are documented guidance
# for authoring, tests, and rider matching — NOT a wire constraint. A non-5e host
# brings its own tags with no protocol change.

DAMAGE_TYPES: frozenset[str] = frozenset({
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
})  # 13

CONDITIONS: frozenset[str] = frozenset({
    "blinded", "charmed", "deafened", "exhaustion", "frightened", "grappled",
    "incapacitated", "invisible", "paralyzed", "petrified", "poisoned", "prone",
    "restrained", "stunned", "unconscious",
})  # 15

STARTER_TAGS: frozenset[str] = DAMAGE_TYPES | CONDITIONS
```

Re-exported from `protocol/__init__.py`: `EffectOp`, `DAMAGE_TYPES`,
`CONDITIONS`, `STARTER_TAGS`, added to `__all__` (kept alphabetically sorted).

## Testing

Plain pytest units in `tests/test_protocol/test_vocabulary.py`:

1. **EffectOp membership (drift guard):** the set of member values is exactly
   `{"reduce", "scale", "negate", "grant_save", "modify_roll", "replace"}` — a
   change to the closed set must be a deliberate edit that also touches this test.
2. **EffectOp is string-valued:** each member equals its string value and
   round-trips through `EffectOp(value)`; `json.dumps`/pydantic serialize it to
   the plain string.
3. **Tag sets:** `DAMAGE_TYPES` and `CONDITIONS` contain their canonical members
   with the expected sizes (13 and 15), are **disjoint**, and
   `STARTER_TAGS == DAMAGE_TYPES | CONDITIONS`.
4. **Public API re-export:** `face_dancer.protocol` exposes `EffectOp`,
   `DAMAGE_TYPES`, `CONDITIONS`, `STARTER_TAGS`.

All code passes `mypy --strict` and the existing ruff config.

## Out of scope

- The `propose_delta` / `apply_delta` delta shape and the `op: EffectOp` field —
  issue #11 consumes this vocabulary; this spike only defines it.
- The rider matcher (op + tag-set comparison) — the rider issue; it will import
  the tag constants defined here.
- Any wire/schema-version change — `SCHEMA_VERSION` stays `1`; this spike adds no
  message type and does not alter an existing one.
- Validation of tags against the starter set on the wire — deliberately not done;
  tags stay open strings.
