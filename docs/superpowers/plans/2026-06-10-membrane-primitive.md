# Membrane Primitive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared membrane primitive (issue #8): a runtime-enforced propose/dispose seam, the epistemic-scope-filter interface, and model-call instrumentation, per the approved spec at `docs/superpowers/specs/2026-06-10-membrane-primitive-design.md`.

**Architecture:** One new package `face_dancer.membrane` containing three orthogonal units — `instrumentation.py` (model-call gateway + contextvar recorder), `scope.py` (Scope/ScopeFilter/PassThroughFilter), and `seam.py` (Proposal/Applied/dispose). The only intra-package dependency is `seam.py` → `instrumentation.py`, so that `dispose()` runs the disposer inside a model-free region. Downstream subsystems (rider, perception, capability, decision) import only the piece they need.

**Tech Stack:** Python 3.11, stdlib only (`dataclasses`, `typing`, `contextvars`, `contextlib`, `abc`). pytest for tests. Tooling: ruff (lint + format), mypy strict on `src`. No new dependencies.

---

## File structure

| File | Responsibility |
|---|---|
| `src/face_dancer/membrane/__init__.py` | Public API re-exports (filled in Task 5; empty docstring before that) |
| `src/face_dancer/membrane/instrumentation.py` | `ModelCall`, `ModelCallRecorder`, `ModelCallForbidden`, `record_model_call`, `recorded_model_calls`, `model_calls_forbidden`, `ModelGateway`, `NullModelGateway` |
| `src/face_dancer/membrane/scope.py` | `Scope`, `ScopeFilter` protocol, `PassThroughFilter` |
| `src/face_dancer/membrane/seam.py` | `Proposal`, `Applied`, `Disposer` protocol, `dispose`, `MembraneViolation` |
| `tests/test_membrane/__init__.py` | Empty test-package marker |
| `tests/test_membrane/test_instrumentation.py` | Recorder, forbidden-region, and gateway tests |
| `tests/test_membrane/test_scope.py` | Pass-through filter and Scope immutability tests |
| `tests/test_membrane/test_seam.py` | Happy path, minting enforcement, model-free-disposal tests |
| `tests/test_membrane/test_api.py` | Public API smoke test |
| `tests/test_hello.py` | Modified: add `face_dancer.membrane` to the importable-submodules list |

**Build order:** instrumentation first (the seam depends on it), then scope, then seam, then the public API. Each task ends green and committed.

**Environment note:** tests import the installed package (src layout). If imports fail with `ModuleNotFoundError: No module named 'face_dancer'`, run `uv pip install -e ".[dev]"` (or `pip install -e ".[dev]"`) once and retry.

---

### Task 1: Recorder and forbidden-region primitives

**Files:**
- Create: `src/face_dancer/membrane/__init__.py`
- Create: `src/face_dancer/membrane/instrumentation.py`
- Create: `tests/test_membrane/__init__.py`
- Test: `tests/test_membrane/test_instrumentation.py`

- [ ] **Step 1: Create the package markers**

Create `src/face_dancer/membrane/__init__.py` with exactly:

```python
"""The membrane: propose/dispose seam, epistemic scope filter, model-call instrumentation."""
```

Create `tests/test_membrane/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_membrane/test_instrumentation.py`:

```python
"""Tests for model-call instrumentation."""

import pytest

from face_dancer.membrane.instrumentation import (
    ModelCall,
    ModelCallForbidden,
    model_calls_forbidden,
    record_model_call,
    recorded_model_calls,
)


def test_recorder_captures_calls_with_path_label() -> None:
    with recorded_model_calls() as rec:
        record_model_call("decision.tactical")
    assert rec.calls == [ModelCall(path="decision.tactical")]


def test_recorder_is_empty_when_path_makes_no_call() -> None:
    with recorded_model_calls() as rec:
        pass
    assert rec.calls == []


def test_recording_without_active_recorder_is_a_no_op() -> None:
    record_model_call("decision.tactical")  # must not raise


def test_forbidden_region_raises_with_reason_and_path() -> None:
    with (
        model_calls_forbidden("disposal is code-only"),
        pytest.raises(ModelCallForbidden) as excinfo,
    ):
        record_model_call("state.write")
    assert excinfo.value.reason == "disposal is code-only"
    assert excinfo.value.path == "state.write"


def test_forbidden_region_resets_after_block() -> None:
    with model_calls_forbidden("temporary"):
        pass
    with recorded_model_calls() as rec:
        record_model_call("free.path")
    assert rec.calls == [ModelCall(path="free.path")]


def test_nested_recorders_stay_isolated() -> None:
    with recorded_model_calls() as outer:
        with recorded_model_calls() as inner:
            record_model_call("inner.path")
        record_model_call("outer.path")
    assert inner.calls == [ModelCall(path="inner.path")]
    assert outer.calls == [ModelCall(path="outer.path")]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_membrane/test_instrumentation.py`
Expected: collection error — `ModuleNotFoundError: No module named 'face_dancer.membrane.instrumentation'` (or `ImportError`). If instead you see `No module named 'face_dancer'`, do the editable install from the environment note, confirm the error becomes the expected one, and continue.

- [ ] **Step 4: Write the implementation**

Create `src/face_dancer/membrane/instrumentation.py`:

```python
"""Model-call instrumentation: contextvar-scoped recording and forbidden regions.

Every model invocation in Face Dancer must pass through a ModelGateway (Task 2),
which reports here. Tests wrap a code path in recorded_model_calls() and assert
the recorder is empty to prove the model stayed off that path (brief AC5).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class ModelCallForbidden(RuntimeError):
    """The model was invoked inside a model_calls_forbidden() region."""

    def __init__(self, reason: str, path: str) -> None:
        super().__init__(f"model call on path {path!r} is forbidden here: {reason}")
        self.reason = reason
        self.path = path


@dataclass(frozen=True)
class ModelCall:
    """One observed model invocation, labelled with the code path that made it."""

    path: str


@dataclass
class ModelCallRecorder:
    """Collects ModelCalls observed within one recorded_model_calls() block."""

    calls: list[ModelCall] = field(default_factory=list)


_recorder: ContextVar[ModelCallRecorder | None] = ContextVar(
    "membrane_model_call_recorder", default=None
)
_forbidden_reason: ContextVar[str | None] = ContextVar(
    "membrane_model_calls_forbidden", default=None
)


def record_model_call(path: str) -> None:
    """Report a model invocation on the current context.

    Raises ModelCallForbidden inside a forbidden region; otherwise appends to
    the active recorder, if any. A no-op when neither is in effect.
    """
    reason = _forbidden_reason.get()
    if reason is not None:
        raise ModelCallForbidden(reason, path)
    recorder = _recorder.get()
    if recorder is not None:
        recorder.calls.append(ModelCall(path=path))


@contextmanager
def recorded_model_calls() -> Iterator[ModelCallRecorder]:
    """Observe model calls made within this block; nests without leaking outward."""
    recorder = ModelCallRecorder()
    token = _recorder.set(recorder)
    try:
        yield recorder
    finally:
        _recorder.reset(token)


@contextmanager
def model_calls_forbidden(reason: str) -> Iterator[None]:
    """Make any model invocation within this block raise ModelCallForbidden."""
    token = _forbidden_reason.set(reason)
    try:
        yield
    finally:
        _forbidden_reason.reset(token)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_membrane/test_instrumentation.py`
Expected: 6 passed.

- [ ] **Step 6: Lint and commit**

```bash
ruff check src tests && ruff format --check src tests
git add src/face_dancer/membrane tests/test_membrane
git commit -m "feat: membrane model-call recorder and forbidden regions (issue #8)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

If `ruff format --check` fails, run `ruff format src tests` and re-stage before committing.

---

### Task 2: ModelGateway and NullModelGateway

**Files:**
- Modify: `src/face_dancer/membrane/instrumentation.py` (append to end)
- Test: `tests/test_membrane/test_instrumentation.py` (append to end)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_membrane/test_instrumentation.py`, and add `NullModelGateway` to the existing import from `face_dancer.membrane.instrumentation` (keep the import list alphabetized — ruff enforces it):

```python
def test_gateway_invoke_records_and_returns_canned_response() -> None:
    gateway = NullModelGateway(response="canned")
    with recorded_model_calls() as rec:
        result = gateway.invoke("decision.expressive", {"prompt": "hi"})
    assert result == "canned"
    assert rec.calls == [ModelCall(path="decision.expressive")]


def test_gateway_invoke_raises_inside_forbidden_region() -> None:
    gateway = NullModelGateway()
    with model_calls_forbidden("no model on this path"), pytest.raises(ModelCallForbidden):
        gateway.invoke("state.write", None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_membrane/test_instrumentation.py`
Expected: collection error — `ImportError: cannot import name 'NullModelGateway'`.

- [ ] **Step 3: Write the implementation**

Append to `src/face_dancer/membrane/instrumentation.py`, and add these imports at the top of the file (below `from __future__ import annotations`):

```python
from abc import ABC, abstractmethod
from typing import final
```

Appended classes:

```python
class ModelGateway(ABC):
    """The single seam every model invocation must pass through.

    invoke() is final so a concrete adapter cannot forget to record; adapters
    implement only _invoke(). The real adapter is deferred (brief non-goal).
    """

    @final
    def invoke(self, path: str, request: object) -> object:
        record_model_call(path)
        return self._invoke(request)

    @abstractmethod
    def _invoke(self, request: object) -> object: ...


class NullModelGateway(ModelGateway):
    """Test double: records like a real gateway, returns a canned response."""

    def __init__(self, response: object = None) -> None:
        self._response = response

    def _invoke(self, request: object) -> object:
        return self._response
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_membrane/test_instrumentation.py`
Expected: 8 passed.

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests && ruff format --check src tests
git add src/face_dancer/membrane/instrumentation.py tests/test_membrane/test_instrumentation.py
git commit -m "feat: membrane ModelGateway seam with null test double (issue #8)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Scope and the epistemic filter interface

**Files:**
- Create: `src/face_dancer/membrane/scope.py`
- Test: `tests/test_membrane/test_scope.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_membrane/test_scope.py`:

```python
"""Tests for the epistemic scope filter interface."""

import dataclasses

import pytest

from face_dancer.membrane.scope import PassThroughFilter, Scope, ScopeFilter


def test_pass_through_filter_returns_payload_unchanged() -> None:
    payload = {"visible": ["goblin"], "hidden": ["assassin"]}
    scope = Scope(subject="char-1", tags=frozenset({"sight"}))
    filt: ScopeFilter[dict[str, list[str]]] = PassThroughFilter()
    assert filt.filter(payload, scope) is payload


def test_scope_is_immutable() -> None:
    scope = Scope(subject="char-1", tags=frozenset())
    with pytest.raises(dataclasses.FrozenInstanceError):
        scope.subject = "char-2"  # type: ignore[misc]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_membrane/test_scope.py`
Expected: collection error — `ModuleNotFoundError: No module named 'face_dancer.membrane.scope'`.

- [ ] **Step 3: Write the implementation**

Create `src/face_dancer/membrane/scope.py`:

```python
"""Epistemic scoping: the filter interface between character and session views.

Rider, perception, capability, and decision each implement ScopeFilter in their
own packages; this module owns only the interface and the trivial pass-through.
filter() is pure — it returns a (possibly narrowed) payload, never mutates one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Scope:
    """One epistemic view: whose it is, and what it may include.

    tags reuses the protocol's set-comparison idiom (brief: rider triggers
    match on tag-sets); the real tag vocabulary arrives with the protocol issue.
    """

    subject: str
    tags: frozenset[str]


class ScopeFilter(Protocol[T]):
    """Narrow a payload to what the given scope is permitted to know."""

    def filter(self, payload: T, scope: Scope) -> T: ...


class PassThroughFilter(Generic[T]):
    """Trivial ScopeFilter: narrows nothing."""

    def filter(self, payload: T, scope: Scope) -> T:
        return payload
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_membrane/test_scope.py`
Expected: 2 passed.

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests && ruff format --check src tests
git add src/face_dancer/membrane/scope.py tests/test_membrane/test_scope.py
git commit -m "feat: membrane Scope and ScopeFilter interface with pass-through (issue #8)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: The propose/dispose seam

**Files:**
- Create: `src/face_dancer/membrane/seam.py`
- Test: `tests/test_membrane/test_seam.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_membrane/test_seam.py`:

```python
"""Tests for the propose/dispose seam: the model proposes, only code disposes."""

import pytest

from face_dancer.membrane.instrumentation import ModelCallForbidden, NullModelGateway
from face_dancer.membrane.seam import Applied, MembraneViolation, Proposal, dispose


def test_dispose_runs_disposer_and_wraps_result() -> None:
    proposal = Proposal(payload=7, origin="model")

    def halve(damage: int) -> int:
        return damage // 2

    applied = dispose(proposal, halve)
    assert isinstance(applied, Applied)
    assert applied.result == 3
    # the proposal is inert and untouched; provenance survives disposal
    assert proposal.payload == 7
    assert proposal.origin == "model"


def test_applied_cannot_be_minted_outside_dispose() -> None:
    with pytest.raises(MembraneViolation):
        Applied(42)


def test_applied_rejects_forged_tokens() -> None:
    with pytest.raises(MembraneViolation):
        Applied(42, object())


def test_dispose_is_a_model_free_region() -> None:
    gateway = NullModelGateway()
    proposal = Proposal(payload="drink potion", origin="model")

    def disposer_that_cheats(payload: str) -> str:
        gateway.invoke("seam.disposal", payload)
        return payload

    with pytest.raises(ModelCallForbidden):
        dispose(proposal, disposer_that_cheats)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_membrane/test_seam.py`
Expected: collection error — `ModuleNotFoundError: No module named 'face_dancer.membrane.seam'`.

- [ ] **Step 3: Write the implementation**

Create `src/face_dancer/membrane/seam.py`:

```python
"""The propose/dispose seam: anyone may propose, only dispose() commits.

A Proposal is inert — holding one changes nothing. Applied is proof of a
commit: its constructor demands a module-private token only dispose()
supplies, so code outside the membrane structurally cannot claim a write
happened. dispose() additionally runs the disposer inside a model-free
region, keeping the model off the write path at runtime, not just in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from face_dancer.membrane.instrumentation import model_calls_forbidden

P = TypeVar("P")
R = TypeVar("R")
P_contra = TypeVar("P_contra", contravariant=True)
R_co = TypeVar("R_co", covariant=True)


class MembraneViolation(RuntimeError):
    """Something other than dispose() tried to mint an Applied."""


_MINT_TOKEN = object()


@dataclass(frozen=True)
class Proposal(Generic[P]):
    """A proposed change. origin records who proposed: "model", "host", ..."""

    payload: P
    origin: str


@dataclass(frozen=True)
class Applied(Generic[R]):
    """Proof that a disposer committed a proposal. Mintable only by dispose()."""

    result: R
    _token: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._token is not _MINT_TOKEN:
            raise MembraneViolation(
                "Applied may only be minted by dispose(); code outside the "
                "membrane cannot claim a write was committed"
            )


class Disposer(Protocol[P_contra, R_co]):
    """The code-side write: consumes a proposal's payload, returns the result."""

    def __call__(self, payload: P_contra) -> R_co: ...


def dispose(proposal: Proposal[P], disposer: Disposer[P, R]) -> Applied[R]:
    """Run the code-side disposer on a proposal inside a model-free region."""
    with model_calls_forbidden(f"disposing proposal from {proposal.origin!r}"):
        result = disposer(proposal.payload)
    return Applied(result, _MINT_TOKEN)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_membrane/test_seam.py`
Expected: 4 passed.

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests && ruff format --check src tests
git add src/face_dancer/membrane/seam.py tests/test_membrane/test_seam.py
git commit -m "feat: membrane propose/dispose seam with runtime minting guard (issue #8)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Public API and full verification

**Files:**
- Modify: `src/face_dancer/membrane/__init__.py` (replace entire file)
- Modify: `tests/test_hello.py` (add one list entry)
- Test: `tests/test_membrane/test_api.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_membrane/test_api.py`:

```python
"""Smoke test: the membrane's public API is importable from the package root."""

from face_dancer import membrane


def test_public_api_names_resolve() -> None:
    assert membrane.__all__, "membrane must declare a public API"
    for name in membrane.__all__:
        assert hasattr(membrane, name), f"missing public name: {name}"
```

In `tests/test_hello.py`, add `"face_dancer.membrane",` to the `SUBMODULES` list, after `"face_dancer.bundle",`:

```python
SUBMODULES = [
    "face_dancer",
    "face_dancer.protocol",
    "face_dancer.bundle",
    "face_dancer.membrane",
    "face_dancer.state",
    "face_dancer.rider",
    "face_dancer.resolution",
    "face_dancer.decision",
    "face_dancer.perception",
    "face_dancer.hosts",
]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_membrane/test_api.py`
Expected: FAIL — `AssertionError: membrane must declare a public API` (the docstring-only `__init__.py` has no `__all__`).

- [ ] **Step 3: Write the implementation**

Replace `src/face_dancer/membrane/__init__.py` entirely with:

```python
"""The membrane: propose/dispose seam, epistemic scope filter, model-call instrumentation.

Every hard boundary in Face Dancer is this one boundary — the model proposes,
code disposes, an epistemic filter sits between. Rider, perception, capability,
and decision each specialize these primitives rather than reinventing them.
"""

from face_dancer.membrane.instrumentation import (
    ModelCall,
    ModelCallForbidden,
    ModelCallRecorder,
    ModelGateway,
    NullModelGateway,
    model_calls_forbidden,
    record_model_call,
    recorded_model_calls,
)
from face_dancer.membrane.scope import PassThroughFilter, Scope, ScopeFilter
from face_dancer.membrane.seam import (
    Applied,
    Disposer,
    MembraneViolation,
    Proposal,
    dispose,
)

__all__ = [
    "Applied",
    "Disposer",
    "MembraneViolation",
    "ModelCall",
    "ModelCallForbidden",
    "ModelCallRecorder",
    "ModelGateway",
    "NullModelGateway",
    "PassThroughFilter",
    "Proposal",
    "Scope",
    "ScopeFilter",
    "dispose",
    "model_calls_forbidden",
    "record_model_call",
    "recorded_model_calls",
]
```

- [ ] **Step 4: Run the full suite and type check**

Run: `pytest`
Expected: all tests pass (15 membrane tests + the existing smoke test).

Run: `mypy`
Expected: `Success: no issues found` (config already targets `src` with strict mode).

Run: `ruff check src tests && ruff format --check src tests`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add src/face_dancer/membrane/__init__.py tests/test_membrane/test_api.py tests/test_hello.py
git commit -m "feat: export membrane public API (issue #8)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
