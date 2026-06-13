# Perception Ingestion + Epistemic Scope Filter

**Issue:** [#21](https://github.com/GeorgeLautenschlager/face-dancer/issues/21)
**Date:** 2026-06-13
**Status:** Approved

## Purpose

Brief §3/§5 — perception is **session → character** and **epistemically scoped**:
the character perceives only what it could plausibly know. This is one instance of
the #8 membrane (the epistemic filter as the boundary). The host's obligation is
to describe the perceivable scene in a standard shape; the character-side filter
narrows it to what *this* character can know.

This issue builds the **scene payload** (the standard shape) and the
**epistemic scope filter** that drops what the character couldn't perceive,
implemented against the #8 `ScopeFilter` interface.

## The division (who decides what the character sees)

The brief's hard constraint — **no host may be assumed to know the character's
rules**, including its perception abilities (truesight, blindsight) — fixes where
the line falls:

- The **host owns the world** and describes the perceivable **Scene**, tagging
  each entity with *what is required to perceive it* (a capability requirement
  and/or a roll-vs-DC check) — **coarse** scoping (only things plausibly present)
  plus per-entity requirements, **never** a final per-character verdict (it can't
  know if this character has truesight).
- The **character-side filter** applies the character's perception **`Scope`** (its
  senses), keeping an entity only if the character meets its requirements.
- The **rider augments the scope** later ("I have truesight" is a character-known
  mechanic the host can't assume). #21 takes the `Scope` as an **input**; deriving
  it (base senses + rider augmentation) is a later integration.

This is why the host sends an imp the character may not see: it sends
`imp, perceivable_with={"truesight"}` because it cannot know the character's
senses; the filter decides. A normal character drops it (AC6); a truesight
character keeps it.

## Decisions

- **Two gate mechanisms, two fields.** An entity carries a deterministic
  **capability** gate `perceivable_with: frozenset[str]` (the perception tags
  required, resolved by pure subset comparison against `scope.tags`) and an
  optional stochastic **roll** gate `check: PerceptionCheck | None` (a `kind` +
  `dc` the character must beat). They are separate because a DC is an `int`
  resolved by a roll, not a tag resolved by set comparison — cramming a DC into the
  frozenset would force a string parser, which the brief forbids. An entity may
  require a capability, a roll, both, or neither.

- **The filter implements the #8 `ScopeFilter` Protocol and is pure.**
  `PerceptionScopeFilter.filter(scene, scope) -> Scene` returns a new `Scene` with
  non-perceivable entities dropped; it never mutates its input (per `scope.py`'s
  contract). It conforms structurally to `ScopeFilter[Scene]`, so it is a drop-in
  alongside the membrane's `PassThroughFilter`.

- **Capability gate works now; the roll gate is pluggable and deferred.** The roll
  engine that resolves a `check` against `sheet.modifier(check.kind)` is a separate
  issue. The filter takes a **constructor-injected** `check_resolver: Callable[[
  PerceptionCheck], bool]`, defaulting to `_drop` (returns `False`): an unrolled
  check means *not perceived* — conservative and correct (the DM hasn't told the
  player what they missed). Constructor injection keeps the
  `filter(scene, scope)` Protocol signature intact. When the roll engine lands, a
  resolver that rolls `sheet.modifier(check.kind)` vs `check.dc` is passed in.

- **Drop whole entities (field-level redaction deferred).** A non-perceivable
  entity is removed entirely; "you see *that* something's there but not *what*"
  is a later refinement.

- **The Scene description is always perceivable.** Only entities are gated; the
  scene-setting prose is the perceivable scene the host chose to describe.

## Architecture

A new pair of modules in the existing `perception/` package.

```
src/face_dancer/perception/
├── __init__.py     # re-exports Scene, Entity, PerceptionCheck, PerceptionScopeFilter (keeps docstring)
├── scene.py        # NEW: Entity, PerceptionCheck, Scene (pydantic payload)
└── filter.py       # NEW: PerceptionScopeFilter + the default _drop resolver
```

Dependency direction: `scene.py` is pydantic-only; `filter.py` imports `Scope`
from `face_dancer.membrane` and the payload types from `scene.py`. `perception →
membrane`, no cycle. The roll engine / sheet are **not** imported (the resolver is
injected).

## The scene payload (`perception/scene.py`)

```python
from pydantic import BaseModel, Field


class PerceptionCheck(BaseModel):
    """A roll-vs-DC gate: the character must beat ``dc`` on a ``kind`` check.

    ``kind`` names the check (e.g. "perception"), resolved later against
    ``sheet.modifier(kind)``; #21 carries it, the roll engine resolves it.
    """

    kind: str
    dc: int


class Entity(BaseModel):
    """A perceivable thing in the scene the character may reference.

    ``perceivable_with`` is the capability gate (perception tags required — empty =
    always perceivable). ``check`` is the optional roll gate. An entity is perceived
    only if both are satisfied.
    """

    name: str
    description: str = ""
    perceivable_with: frozenset[str] = frozenset()
    check: PerceptionCheck | None = None


class Scene(BaseModel):
    """The standard perceivable-scene payload the host sends (session -> character)."""

    description: str = ""
    entities: list[Entity] = Field(default_factory=list)
```

## The epistemic filter (`perception/filter.py`)

```python
from collections.abc import Callable

from face_dancer.membrane import Scope
from face_dancer.perception.scene import PerceptionCheck, Scene


def _drop(check: PerceptionCheck) -> bool:
    """Default check resolver: an unrolled check is treated as failed (not perceived)."""
    return False


class PerceptionScopeFilter:
    """Narrow a Scene to what a character's perception scope permits (a ScopeFilter).

    The capability gate (``perceivable_with`` vs ``scope.tags``) is resolved here;
    the roll gate (``check``) is delegated to ``check_resolver`` (default: drop).
    Pure — returns a new Scene, never mutates the input.
    """

    def __init__(self, check_resolver: Callable[[PerceptionCheck], bool] = _drop) -> None:
        self._resolve = check_resolver

    def filter(self, payload: Scene, scope: Scope) -> Scene:
        return Scene(
            description=payload.description,
            entities=[
                e
                for e in payload.entities
                if e.perceivable_with <= scope.tags
                and (e.check is None or self._resolve(e.check))
            ],
        )
```

Re-exported from `perception/__init__.py` (keep the docstring): `Scene`, `Entity`,
`PerceptionCheck`, `PerceptionScopeFilter`.

## Testing

`tests/test_perception/test_scene.py`:

1. **Defaults / round-trip:** `Entity(name="goblin")` has empty `perceivable_with`,
   `check is None`; a populated `Scene` (entities with tags + a `check`) round-trips
   python + JSON (`==`).

`tests/test_perception/test_filter.py`:

2. **Keeps always-perceivable entities + the description:** a `Scene` of entities
   with empty `perceivable_with` and no `check`, filtered under any scope, returns
   all entities and the same `description`.
3. **AC6 — drops a capability-gated entity the scope can't meet:** an entity with
   `perceivable_with={"truesight"}` filtered under `Scope(subject="c",
   tags=frozenset({"sight"}))` is **absent** from the result.
4. **Keeps it when the scope has the tag:** the same entity under
   `Scope(tags=frozenset({"sight", "truesight"}))` is **present** (the rider-reveal
   case).
5. **Check gate, default resolver drops:** an entity with
   `check=PerceptionCheck(kind="perception", dc=15)` (and a satisfiable
   `perceivable_with`) is dropped by a default `PerceptionScopeFilter()`.
6. **Check gate, injected resolver keeps:** with
   `PerceptionScopeFilter(check_resolver=lambda c: True)`, that entity is kept;
   with `lambda c: c.dc <= 10`, a DC-15 entity is dropped and a DC-10 one kept.
7. **Purity:** filtering does not mutate the input `Scene` (its `entities` list is
   unchanged in length/content).
8. **ScopeFilter conformance:** a `PerceptionScopeFilter` is usable where a
   `ScopeFilter[Scene]` is expected (annotate `flt: ScopeFilter[Scene] =
   PerceptionScopeFilter()` and call `flt.filter(scene, scope)`), behaving as a
   drop-in alongside `PassThroughFilter`.
9. **Public API:** `face_dancer.perception` re-exports all four names.

`tests/test_perception/__init__.py` empty package marker. All code passes
`mypy --strict` and the existing ruff config.

## Out of scope

- **Deriving the character's `Scope`** (base senses + rider augmentation) — a later
  integration; the scope is an input here.
- **The roll engine** that resolves a `check` against `sheet.modifier(kind)` — its
  own issue; #21 ships the default-drop resolver and the injection point.
- **The decision / intent generation** (#24) that would consume the scoped scene —
  AC6's "intents don't reference the entity" is realized there; #21 establishes the
  precondition (the entity is absent from the perceived scene).
- **Field-level redaction** (partial knowledge of an entity) — drop whole entities
  for v0.
- The **host side** that produces the scene.
