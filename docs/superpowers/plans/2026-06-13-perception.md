# Perception + Epistemic Scope Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the perceivable-`Scene` payload (entities with capability + roll perception gates) and the pure `PerceptionScopeFilter` that drops what a character's `Scope` can't perceive (a #8 `ScopeFilter`).

**Architecture:** `perception/scene.py` holds three pydantic models (`Entity`, `PerceptionCheck`, `Scene`). `perception/filter.py` holds `PerceptionScopeFilter`, which resolves the deterministic capability gate (`perceivable_with ⊆ scope.tags`) and delegates the roll gate (`check`) to a constructor-injected resolver (default drops). No bundle/roll-engine dependency.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-perception-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's new modules. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **117 passed**.

---

## Task 1: The scene payload (`perception/scene.py`)

**Files:**
- Create: `src/face_dancer/perception/scene.py`
- Modify: `src/face_dancer/perception/__init__.py`
- Test: `tests/test_perception/__init__.py`, `tests/test_perception/test_scene.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_perception/__init__.py` as an **empty file** (package marker).

Create `tests/test_perception/test_scene.py`:

```python
"""Tests for the perceivable-scene payload."""

from face_dancer.perception.scene import Entity, PerceptionCheck, Scene


def test_entity_defaults() -> None:
    e = Entity(name="goblin")
    assert e.description == ""
    assert e.perceivable_with == frozenset()
    assert e.check is None


def test_scene_round_trips_through_python_and_json() -> None:
    scene = Scene(
        description="A torchlit cavern.",
        entities=[
            Entity(name="goblin", description="snarling"),
            Entity(
                name="imp",
                perceivable_with=frozenset({"truesight"}),
                check=PerceptionCheck(kind="perception", dc=15),
            ),
        ],
    )
    assert Scene.model_validate(scene.model_dump()) == scene
    assert Scene.model_validate_json(scene.model_dump_json()) == scene
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_perception/test_scene.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.perception.scene'`.

- [ ] **Step 3: Write the scene module**

Create `src/face_dancer/perception/scene.py`:

```python
"""The perceivable-scene payload: a scene of entities with perception gates."""

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

- [ ] **Step 4: Re-export the scene types**

Edit `src/face_dancer/perception/__init__.py` — KEEP the existing module docstring at the top, and add below it:

```python
from face_dancer.perception.scene import Entity, PerceptionCheck, Scene

__all__ = ["Entity", "PerceptionCheck", "Scene"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_perception/test_scene.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/perception/scene.py src/face_dancer/perception/__init__.py tests/test_perception
git commit -m "feat(perception): add the perceivable-scene payload (issue #21)"
```

---

## Task 2: The epistemic scope filter (`perception/filter.py`)

**Files:**
- Create: `src/face_dancer/perception/filter.py`
- Modify: `src/face_dancer/perception/__init__.py`
- Test: `tests/test_perception/test_filter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_perception/test_filter.py`:

```python
"""Tests for the perception epistemic scope filter."""

from face_dancer.membrane import PassThroughFilter, Scope, ScopeFilter
from face_dancer.perception.filter import PerceptionScopeFilter
from face_dancer.perception.scene import Entity, PerceptionCheck, Scene


def _names(scene: Scene) -> set[str]:
    return {e.name for e in scene.entities}


def test_keeps_always_perceivable_entities_and_description() -> None:
    scene = Scene(
        description="cavern",
        entities=[Entity(name="goblin"), Entity(name="torch")],
    )
    result = PerceptionScopeFilter().filter(scene, Scope(subject="c", tags=frozenset()))
    assert _names(result) == {"goblin", "torch"}
    assert result.description == "cavern"


def test_drops_capability_gated_entity_the_scope_cannot_meet() -> None:
    scene = Scene(entities=[Entity(name="imp", perceivable_with=frozenset({"truesight"}))])
    result = PerceptionScopeFilter().filter(
        scene, Scope(subject="c", tags=frozenset({"sight"}))
    )
    assert _names(result) == set()  # AC6: hidden entity omitted


def test_keeps_capability_gated_entity_when_scope_has_the_tag() -> None:
    scene = Scene(entities=[Entity(name="imp", perceivable_with=frozenset({"truesight"}))])
    result = PerceptionScopeFilter().filter(
        scene, Scope(subject="c", tags=frozenset({"sight", "truesight"}))
    )
    assert _names(result) == {"imp"}


def test_check_gated_entity_dropped_by_default_resolver() -> None:
    scene = Scene(
        entities=[Entity(name="trap", check=PerceptionCheck(kind="perception", dc=15))]
    )
    result = PerceptionScopeFilter().filter(scene, Scope(subject="c", tags=frozenset()))
    assert _names(result) == set()


def test_check_gated_entity_kept_with_injected_resolver() -> None:
    scene = Scene(
        entities=[
            Entity(name="easy", check=PerceptionCheck(kind="perception", dc=10)),
            Entity(name="hard", check=PerceptionCheck(kind="perception", dc=15)),
        ]
    )
    flt = PerceptionScopeFilter(check_resolver=lambda c: c.dc <= 10)
    result = flt.filter(scene, Scope(subject="c", tags=frozenset()))
    assert _names(result) == {"easy"}


def test_filter_is_pure() -> None:
    scene = Scene(entities=[Entity(name="imp", perceivable_with=frozenset({"truesight"}))])
    PerceptionScopeFilter().filter(scene, Scope(subject="c", tags=frozenset()))
    assert len(scene.entities) == 1  # input untouched


def test_conforms_to_scopefilter_interface() -> None:
    scene = Scene(entities=[Entity(name="goblin")])
    scope = Scope(subject="c", tags=frozenset())
    filters: list[ScopeFilter[Scene]] = [PassThroughFilter(), PerceptionScopeFilter()]
    for flt in filters:
        assert isinstance(flt.filter(scene, scope), Scene)


def test_public_api_is_reexported() -> None:
    import face_dancer.perception as perception

    for name in ("Scene", "Entity", "PerceptionCheck", "PerceptionScopeFilter"):
        assert hasattr(perception, name)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_perception/test_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.perception.filter'`.

- [ ] **Step 3: Write the filter module**

Create `src/face_dancer/perception/filter.py`:

```python
"""The perception epistemic scope filter: narrow a Scene to a character's senses."""

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

- [ ] **Step 4: Add the filter to the package re-exports**

Edit `src/face_dancer/perception/__init__.py` so the import block and `__all__`
become (keep the module docstring above):

```python
from face_dancer.perception.filter import PerceptionScopeFilter
from face_dancer.perception.scene import Entity, PerceptionCheck, Scene

__all__ = ["Entity", "PerceptionCheck", "PerceptionScopeFilter", "Scene"]
```

- [ ] **Step 5: Run the perception suite to verify it passes**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_perception -v`
Expected: PASS (10 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/perception/filter.py src/face_dancer/perception/__init__.py tests/test_perception/test_filter.py
git commit -m "feat(perception): add the epistemic scope filter (issue #21)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~127 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from face_dancer.membrane import Scope
from face_dancer.perception import Scene, Entity, PerceptionScopeFilter
scene = Scene(entities=[Entity(name='goblin'),
                        Entity(name='imp', perceivable_with=frozenset({'truesight'}))])
seen = PerceptionScopeFilter().filter(scene, Scope(subject='c', tags=frozenset({'sight'})))
print(sorted(e.name for e in seen.entities))
"
# ['goblin']
```

## Out of scope (do NOT implement)

- Deriving the character's `Scope` (base senses + rider augmentation).
- The roll engine that resolves a `check` against `sheet.modifier(kind)` (ship the default-drop resolver + the injection point only).
- The decision / intent generation (#24); the host side.
- Field-level redaction (drop whole entities for v0).
