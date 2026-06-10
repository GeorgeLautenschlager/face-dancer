# The Membrane Primitive + Epistemic-Filter Scaffold

**Issue:** [#8](https://github.com/GeorgeLautenschlager/face-dancer/issues/8)
**Date:** 2026-06-10
**Status:** Approved

## Purpose

Every hard boundary in Face Dancer is the same boundary: the character owns/knows X, the session owns/knows Y; the model proposes and code disposes; an epistemic-scope filter sits between them. Rider, perception, capability, and decision policy are four instances of that one pattern. This spec defines the shared primitive they each specialize, so the invariant is enforced in one place.

Three deliverables:

1. A typed **propose/dispose seam**: the model may propose, only code may dispose (write/commit), enforced at runtime.
2. An **epistemic-scope-filter interface** that downstream subsystems implement, with a trivial pass-through implementation.
3. **Model-call instrumentation** so "no model call on this path" is assertable (supports acceptance criterion 5 of the brief).

## Decisions

- **Runtime-enforced seam** — proposals are inert wrapper types; only `dispose()` can mint an `Applied` result, and constructing one elsewhere raises. Chosen over type-level-only checking and over convention-plus-instrumentation.
- **Gateway + contextvar recorder** — all model invocations pass through one `ModelGateway` seam, observed by a contextvar-scoped recorder. Chosen over explicit DI (threads a parameter through every signature forever) and a global counter (flaky under parallel tests).
- **Fully generic** — the primitive is generic over payload type. Concrete protocol shapes (`propose_delta` / `apply_delta`) come in their own issue and specialize it.
- **Three orthogonal pieces, one package** — seam, filter, and instrumentation are independent units in `face_dancer.membrane`; subsystems take only what they need. Chosen over a single `Membrane` class (couples concerns, framework-y) and bare functions (no runtime guarantee, no named interface).
- **Disposal is a model-free region** — `dispose()` runs the disposer inside `model_calls_forbidden()`, turning "the model stays off the write path" from a test-time assertion into a runtime guarantee. This is the one permitted intra-package dependency: `seam.py` imports `instrumentation.py`.

## Architecture

New package `src/face_dancer/membrane/`, below the subsystem packages (they import it; it imports none of them). Stdlib only — `dataclasses`, `typing`, `contextvars`, `contextlib`. No new dependencies.

```
src/face_dancer/membrane/
├── __init__.py        # re-exports the public API
├── seam.py            # Proposal[P], Applied[R], dispose(), Disposer protocol
├── scope.py           # Scope, ScopeFilter protocol, PassThroughFilter
└── instrumentation.py # ModelGateway base, ModelCallRecorder, context managers
```

`scope.py` and `instrumentation.py` import nothing from each other. `seam.py` imports `instrumentation.py` only for the forbidden-region guard.

## The propose/dispose seam (`seam.py`)

Generic over a payload type `P` and a result type `R`:

```python
@dataclass(frozen=True)
class Proposal(Generic[P]):
    payload: P
    origin: str          # who proposed: "model", "host", "rider", ...

@dataclass(frozen=True)
class Applied(Generic[R]):
    result: R
    # constructor guarded: raises MembraneViolation unless minted by dispose()

class Disposer(Protocol[P, R]):
    def __call__(self, payload: P) -> R: ...

def dispose(proposal: Proposal[P], disposer: Callable[[P], R]) -> Applied[R]: ...
```

Three properties carry the invariant:

1. **Anyone can propose.** `Proposal` is a plain frozen dataclass — model-side code constructs them freely. Holding one changes nothing.
2. **Only `dispose()` can mint `Applied`.** `Applied.__post_init__` checks a module-private token that only `dispose()` supplies; direct construction raises `MembraneViolation`. Downstream code structurally cannot fake "this was committed."
3. **Disposal is a model-free region.** `dispose()` runs the disposer inside `model_calls_forbidden()`. Any model-gateway invocation in the disposer's dynamic extent raises `ModelCallForbidden`.

`origin` is a plain string, not an enum — subsystems that specialize the seam own their own vocabulary; the membrane just preserves provenance.

`dispose` is annotated with `Callable[[P], R]` rather than `Disposer` because mypy cannot infer the result type through a generic Protocol parameter; `Disposer` remains the named interface that class-based disposers implement.

## The epistemic scope filter (`scope.py`)

The interface rider, perception, capability, and decision each implement:

```python
@dataclass(frozen=True)
class Scope:
    subject: str              # whose epistemic view, e.g. a character id
    tags: frozenset[str]      # what this view is permitted to include

class ScopeFilter(Protocol[T]):
    def filter(self, payload: T, scope: Scope) -> T: ...

class PassThroughFilter(Generic[T]):   # the definition-of-done trivial implementation
    def filter(self, payload: T, scope: Scope) -> T:
        return payload
```

`filter` is pure: it returns a (possibly narrowed) payload and never mutates its input. `Scope.tags` reuses the set-comparison idiom the brief chose for rider triggers, so when the protocol issue defines the real tag vocabulary, scopes speak it for free. Nothing else goes into `Scope` until a subsystem demonstrates the need.

## Instrumentation (`instrumentation.py`)

Two halves: a gateway every model invocation must pass through, and a contextvar-scoped recorder that observes it.

```python
class ModelGateway(ABC):
    def invoke(self, path: str, request: object) -> object:   # final: records, then delegates
        record_model_call(path)
        return self._invoke(request)

    @abstractmethod
    def _invoke(self, request: object) -> object: ...

@contextmanager
def recorded_model_calls() -> Iterator[ModelCallRecorder]: ...   # rec.calls: list[ModelCall]

@contextmanager
def model_calls_forbidden(reason: str) -> Iterator[None]: ...    # any call raises ModelCallForbidden
```

The template method on `ModelGateway` means a concrete adapter (deferred per the brief) cannot forget to record — it only implements `_invoke`. The `path` argument is a free-form label naming the code path; tests wrap a path in `recorded_model_calls()` and assert the recorder is empty, which is exactly what acceptance criterion 5 needs. The contextvar makes recorders nest correctly and stay isolated under parallel or async tests.

A `NullModelGateway` test double (returns a canned response) ships in the package so tests can exercise the recorder without a real model.

## Error handling

Two exception types, both programming errors that must never be caught and continued:

- `MembraneViolation` — something other than `dispose()` tried to mint an `Applied`; code is claiming authority it doesn't have.
- `ModelCallForbidden` — the model gateway was invoked inside a `model_calls_forbidden()` region (including the one `dispose()` establishes). Carries the `reason` and the offending `path` label so the traceback names both the protected region and the violator.

No error codes, no recovery paths — these crash loudly by design, because each one means the core invariant was breached.

## Testing

Plain pytest units in `tests/test_membrane/`:

1. Propose → dispose → `Applied` happy path: disposer runs, result is wrapped, payload provenance preserved.
2. Constructing `Applied` directly raises `MembraneViolation`.
3. `PassThroughFilter` returns the payload unchanged (the definition-of-done test).
4. `recorded_model_calls()` captures an invocation through `NullModelGateway` with its `path` label, and records nothing when the path makes no call.
5. A disposer that invokes the gateway inside `dispose()` raises `ModelCallForbidden`.
6. Nested recorders stay isolated — the inner recorder doesn't leak calls into the outer scope, and the contextvar resets after the block.

All code passes `mypy --strict` and the existing ruff config.

## Out of scope

- Concrete protocol shapes (`propose_delta`, `apply_delta`, `contest`, `intent`) — their own issue.
- Any real model adapter — `ModelGateway` is the seam; adapters are deferred per the brief's non-goals.
- Subsystem-specific filters (rider matching, perception scoping) — they implement `ScopeFilter` in their own issues.
