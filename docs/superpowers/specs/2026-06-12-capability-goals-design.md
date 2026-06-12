# Capability Interface + Goals at Three Timescales

**Issue:** [#22](https://github.com/GeorgeLautenschlager/face-dancer/issues/22)
**Date:** 2026-06-12
**Status:** Approved

## Purpose

Brief §3/§5 — **capability is character-known; affordance (what's legal now) is
session-known.** The character declares what it *can* do (proactive — the home
for "I can cast Fireball") and proposes; the session validates. The character
**never enumerates its own legal moves.** Goals bias the decision at three
timescales: persistent drives (from persona), situational objectives (scene-level,
often host-supplied), tactical intent (per turn).

This issue defines the **inputs** the decision policy consumes: a `Capability`
model and its capability→`intent` feed, and a three-timescale `Goals`
representation. The decision *policy itself* is issue
[#24](https://github.com/GeorgeLautenschlager/face-dancer/issues/24); this issue
builds the representation it reads.

## Decisions

- **`Capability` carries `name`, `description`, `tags`** — `name` is the
  host-understood action reference that becomes `Intent.action`; `description` is
  prose the (LLM) decision step reads to choose and a host may render; `tags` reuse
  the #3 tag vocabulary (`frozenset[str]`, default empty) so a capability can later
  correlate with the rider and perception tag-matching. No capability internals /
  parameters — deferred, mirroring how the protocol kept references open.

- **A capability feeds intent generation via `to_intent`** — `Capability.to_intent`
  produces an `Intent` whose `action` is the capability's `name`; the decision step
  picks the capability and supplies `target` / `narration`. This is the DoD's
  "capabilities are declared and feed intent generation," made concrete and
  testable.

- **No enumeration of session-owned legality (the DoD)** — `Capability` has no
  availability/legality field, and the `capability` package exposes **no**
  "legal_moves" / "available_actions" function. The character declares what it
  *can* do; what's legal now is the session's to decide. A field-set drift-guard
  test pins `Capability`'s fields so a legality field cannot be added silently.

- **`Goals` is three prose-string fields** — `persistent_drives: list[str]`,
  `situational_objectives: list[str]`, `tactical_intent: str | None`. Simple prose
  the LLM decision step reads to bias choices (per #6: keep it simple). Numeric
  priority/weighting is deferred until the decision policy (#24) actually needs it.

- **Empty `situational_objectives` is the #6 fallback** — when the host supplies no
  situational objective, the list is empty and the character does **not** infer one
  (real inference is inseparable from the deferred memory systems). The decision
  biases on persistent drives + tactical intent only. `persistent_drives` are the
  simple persona-derived v0 source; both may later migrate into memory.

- **Placement: `Capability` in its own `capability/` package; `Goals` in
  `decision/`** — capability is a distinct seam (the brief's "action interface";
  `membrane/scope.py` already names "capability" as one of the four packages).
  Goals bias the decision, so they live in the `decision` package the policy (#24)
  will fill. Both are pydantic models (consistent with `DynamicState` / `Delta`).

- **Representation only; persistence deferred** — #22 touches no bundle. Where
  capabilities and persistent drives persist (a 4th bundle slot vs. folded into the
  sheet #16) is a separate, later integration. These models are **not** wire
  protocol, so there is no `schema.json` or `SCHEMA_VERSION` change.

- **`ScopeFilter` / membrane integration deferred** — the brief frames capability
  as one of four instances of the membrane pattern. #22 honors that boundary
  through the *no-legality* property (the character proposes from its capabilities;
  the session disposes/validates), not by implementing a `ScopeFilter` yet. The
  epistemic-filter integration lands when perception/decision need it.

## Architecture

```
src/face_dancer/capability/        # NEW package — the action interface
├── __init__.py                    # re-exports Capability
└── capability.py                  # Capability model + to_intent

src/face_dancer/decision/
├── __init__.py                    # re-exports Goals (keeps existing docstring)
└── goals.py                       # NEW: Goals (three-timescale prose inputs)
```

Dependency direction: `capability/capability.py` imports `Intent` from
`face_dancer.protocol` (to build the intent); `decision/goals.py` imports only
pydantic + stdlib. No cycles. Neither imports the bundle.

## The `Capability` model (`capability/capability.py`)

```python
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
```

Re-exported from `capability/__init__.py` with `__all__ = ["Capability"]`.

## The `Goals` model (`decision/goals.py`)

```python
from pydantic import BaseModel, Field


class Goals(BaseModel):
    """Goals biasing the decision at three timescales.

    ``persistent_drives`` come from persona; ``situational_objectives`` are
    scene-level and host-supplied (empty = the #6 fallback: no inference, bias on
    drives + tactical intent only); ``tactical_intent`` is the per-turn aim.
    Prose the decision policy reads.
    """

    persistent_drives: list[str] = Field(default_factory=list)
    situational_objectives: list[str] = Field(default_factory=list)
    tactical_intent: str | None = None
```

Re-exported from `decision/__init__.py` (keep the existing module docstring),
`__all__ = ["Goals"]`.

## Testing

`tests/test_capability/test_capability.py`:

1. **Construction / defaults:** `Capability(name="cast fireball", description="...")`
   has `tags == frozenset()`; a tagged capability keeps its tags.
2. **Round-trip:** `Capability.model_validate(c.model_dump()) == c` (python + JSON).
3. **`to_intent` feed:** `cap.to_intent(correlation_id=cid)` returns an `Intent`
   with `action == cap.name`, `target is None`, `narration is None`; supplying
   `target`/`narration` carries them through. The produced intent carries no
   legality (it's a plain `Intent`).
4. **No-legality field guard:** `set(Capability.model_fields) == {"name",
   "description", "tags"}` — a legality/availability field can't be added silently.
5. **Public API:** `face_dancer.capability` re-exports `Capability`.

`tests/test_decision/test_goals.py`:

6. **Construction / defaults:** `Goals()` has empty `persistent_drives`, empty
   `situational_objectives` (the #6 fallback), `tactical_intent is None`.
7. **Round-trip:** a populated `Goals` round-trips (python + JSON).
8. **Public API:** `face_dancer.decision` re-exports `Goals`.

All code passes `mypy --strict` and the existing ruff config.

## Out of scope

- The **decision policy** (choosing a capability, routing tactical vs. expressive) —
  issue #24; #22 only provides the inputs.
- **Bundle persistence** of capabilities / persistent drives — a later integration
  (4th slot vs. sheet #16).
- **A `ScopeFilter`** for the capability seam — deferred; the no-legality property
  covers the membrane boundary for now.
- **Capability parameters / cost**, goal priority/weighting — deferred until a
  consumer needs them.
- The **sheet (#16)**, **rider (#18)**, **perception (#21)** schemas.
