# Capability Interface + Goals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the decision-layer inputs — a `Capability` model (with a capability→`intent` feed) in a new `capability/` package, and a three-timescale `Goals` model in `decision/`.

**Architecture:** Two small pydantic models. `Capability` (name/description/tags) lives in a new `capability/` package and exposes `to_intent` (its `name` becomes `Intent.action`); it declares what the character *can* do and carries no legality field. `Goals` (three prose-string fields) lives in `decision/`. Neither touches the bundle; neither is wire protocol (no schema/version change).

**Tech Stack:** Python 3.11+, pydantic v2, pytest, ruff, mypy (strict). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-12-capability-goals-design.md`

---

## Environment note (read before running any command)

This work happens in a git worktree. The `face_dancer` package is editable-installed from the **main** checkout, so a bare `pytest`/`mypy` imports the main tree and will NOT see this worktree's new packages. **Every** command below sets the path to this worktree's `src`, run from the worktree root:

- Tests: `PYTHONPATH="$PWD/src" python3 -m pytest ...`
- Types: `MYPYPATH="$PWD/src" mypy src`

Baseline before any change: `PYTHONPATH="$PWD/src" python3 -m pytest -q` → **87 passed**.

---

## Task 1: The `Capability` interface (new `capability/` package)

**Files:**
- Create: `src/face_dancer/capability/__init__.py`
- Create: `src/face_dancer/capability/capability.py`
- Test: `tests/test_capability/__init__.py`, `tests/test_capability/test_capability.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capability/__init__.py` as an **empty file** (package marker).

Create `tests/test_capability/test_capability.py`:

```python
"""Tests for the Capability model and its intent feed."""

from uuid import uuid4

from face_dancer.capability.capability import Capability
from face_dancer.protocol import Intent


def test_defaults_to_empty_tags() -> None:
    cap = Capability(name="cast fireball", description="hurl a bolt of flame")
    assert cap.name == "cast fireball"
    assert cap.description == "hurl a bolt of flame"
    assert cap.tags == frozenset()


def test_keeps_tags() -> None:
    cap = Capability(name="cast fireball", description="x", tags=frozenset({"fire"}))
    assert cap.tags == frozenset({"fire"})


def test_round_trips_through_python_and_json() -> None:
    cap = Capability(name="cast fireball", description="x", tags=frozenset({"fire"}))
    assert Capability.model_validate(cap.model_dump()) == cap
    assert Capability.model_validate_json(cap.model_dump_json()) == cap


def test_to_intent_uses_name_as_action() -> None:
    cap = Capability(name="cast fireball", description="x")
    cid = uuid4()
    intent = cap.to_intent(correlation_id=cid)
    assert isinstance(intent, Intent)
    assert intent.action == "cast fireball"
    assert intent.correlation_id == cid
    assert intent.target is None
    assert intent.narration is None


def test_to_intent_carries_target_and_narration() -> None:
    cap = Capability(name="cast fireball", description="x")
    intent = cap.to_intent(
        correlation_id=uuid4(), target="goblin", narration="Melian hurls a fireball."
    )
    assert intent.target == "goblin"
    assert intent.narration == "Melian hurls a fireball."


def test_capability_has_no_legality_field() -> None:
    # The character declares what it CAN do, never what is legal now. A legality /
    # availability field must be a deliberate edit that trips this guard.
    assert set(Capability.model_fields) == {"name", "description", "tags"}


def test_public_api_is_reexported() -> None:
    import face_dancer.capability as capability

    assert hasattr(capability, "Capability")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_capability -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.capability'`.

- [ ] **Step 3: Write the `Capability` model**

Create `src/face_dancer/capability/capability.py`:

```python
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
```

- [ ] **Step 4: Write the package `__init__.py`**

Create `src/face_dancer/capability/__init__.py`:

```python
"""Capability interface — the character's proactive 'what I can do'.

Capabilities are character-known and feed intent generation; affordance (what is
legal now) is session-owned, so the character proposes and never enumerates its
own legal moves.
"""

from face_dancer.capability.capability import Capability

__all__ = ["Capability"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_capability -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean. (If format flags the new files, run `ruff format src tests` and re-check.)

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/capability tests/test_capability
git commit -m "feat(capability): add Capability model with intent feed (issue #22)"
```

---

## Task 2: The three-timescale `Goals` model (`decision/`)

**Files:**
- Create: `src/face_dancer/decision/goals.py`
- Modify: `src/face_dancer/decision/__init__.py`
- Test: `tests/test_decision/__init__.py`, `tests/test_decision/test_goals.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_decision/__init__.py` as an **empty file** (package marker).

Create `tests/test_decision/test_goals.py`:

```python
"""Tests for the three-timescale Goals model."""

from face_dancer.decision.goals import Goals


def test_defaults_are_the_fallback() -> None:
    g = Goals()
    assert g.persistent_drives == []
    assert g.situational_objectives == []  # empty = the #6 fallback (no inference)
    assert g.tactical_intent is None


def test_round_trips_through_python_and_json() -> None:
    g = Goals(
        persistent_drives=["protect the weak"],
        situational_objectives=["reach the bridge"],
        tactical_intent="flank the archer",
    )
    assert Goals.model_validate(g.model_dump()) == g
    assert Goals.model_validate_json(g.model_dump_json()) == g


def test_public_api_is_reexported() -> None:
    import face_dancer.decision as decision

    assert hasattr(decision, "Goals")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_decision -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'face_dancer.decision.goals'`.

- [ ] **Step 3: Write the `Goals` model**

Create `src/face_dancer/decision/goals.py`:

```python
"""The Goals model: goal inputs biasing the decision at three timescales."""

from pydantic import BaseModel, Field


class Goals(BaseModel):
    """Goals biasing the decision at three timescales.

    ``persistent_drives`` come from persona; ``situational_objectives`` are
    scene-level and host-supplied (empty = the #6 fallback: no inference, bias on
    drives + tactical intent only); ``tactical_intent`` is the per-turn aim. Prose
    the decision policy reads.
    """

    persistent_drives: list[str] = Field(default_factory=list)
    situational_objectives: list[str] = Field(default_factory=list)
    tactical_intent: str | None = None
```

- [ ] **Step 4: Re-export from the decision package**

Edit `src/face_dancer/decision/__init__.py` — KEEP the existing module docstring at the top, and add below it:

```python
from face_dancer.decision.goals import Goals

__all__ = ["Goals"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH="$PWD/src" python3 -m pytest tests/test_decision -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint, format, type-check**

Run: `ruff check src tests && ruff format --check src tests && MYPYPATH="$PWD/src" mypy src`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/face_dancer/decision/goals.py src/face_dancer/decision/__init__.py tests/test_decision
git commit -m "feat(decision): add three-timescale Goals model (issue #22)"
```

---

## Verification (end-to-end)

From the worktree root:

```bash
PYTHONPATH="$PWD/src" python3 -m pytest -q           # all green (~97 tests)
ruff check src tests                                  # All checks passed!
ruff format --check src tests                         # all files formatted
MYPYPATH="$PWD/src" mypy src                           # Success: no issues found
PYTHONPATH="$PWD/src" python3 -c "
from uuid import uuid4
from face_dancer.capability import Capability
from face_dancer.decision import Goals
cap = Capability(name='cast fireball', description='x', tags=frozenset({'fire'}))
i = cap.to_intent(correlation_id=uuid4(), target='goblin')
print(i.action, i.target, sorted(cap.tags))
print(Goals().situational_objectives == [])
"
# cast fireball goblin ['fire']
# True
```

## Out of scope (do NOT implement)

- The decision policy (choosing a capability, tactical/expressive routing) — #24.
- Bundle persistence of capabilities / persistent drives; any bundle change.
- A `ScopeFilter` for the capability seam; capability parameters/cost; goal weights.
- Any `schema.json` or `SCHEMA_VERSION` change (these are not wire-protocol models).
