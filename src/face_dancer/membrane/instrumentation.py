"""Model-call instrumentation: contextvar-scoped recording and forbidden regions.

Every model invocation in Face Dancer must pass through a ModelGateway (Task 2),
which reports here. Tests wrap a code path in recorded_model_calls() and assert
the recorder is empty to prove the model stayed off that path (brief AC5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import final


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
    # forbidden takes priority over recording: a guarded region must raise,
    # never silently record, even when a recorder is active
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


class ModelGateway(ABC):
    """The single seam every model invocation must pass through.

    invoke() records then delegates; adapters implement only _invoke(), so
    recording cannot be forgotten. Overriding invoke() raises TypeError at
    class-definition time (and is additionally flagged by mypy via @final).
    The real adapter is deferred (brief non-goal).
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "invoke" in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} may not override ModelGateway.invoke(); "
                "implement _invoke() instead"
            )

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
