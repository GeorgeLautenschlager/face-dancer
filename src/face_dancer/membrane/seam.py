"""The propose/dispose seam: anyone may propose, only dispose() commits.

A Proposal is inert — holding one changes nothing. Applied is proof of a
commit: its constructor demands a module-private token only dispose()
supplies, so code outside the membrane structurally cannot claim a write
happened. dispose() additionally runs the disposer inside a model-free
region, keeping the model off the write path at runtime, not just in tests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from face_dancer.membrane.instrumentation import model_calls_forbidden

P = TypeVar("P")
R = TypeVar("R")
P_contra = TypeVar("P_contra", contravariant=True)
R_co = TypeVar("R_co", covariant=True)


class MembraneViolation(RuntimeError):
    """Something other than dispose() tried to mint an Applied."""


# A single underscore is a convention, not an enforcement mechanism — a
# determined caller can still import this. Accepted tradeoff: the guard
# stops accidental forgery, not adversarial Python.
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

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError(
            f"{cls.__name__}: Applied may not be subclassed; "
            "its constructor guard must not be overridable"
        )

    def __post_init__(self) -> None:
        if self._token is not _MINT_TOKEN:
            raise MembraneViolation(
                "Applied may only be minted by dispose(); code outside the "
                "membrane cannot claim a write was committed"
            )


class Disposer(Protocol[P_contra, R_co]):
    """The code-side write: consumes a proposal's payload, returns the result."""

    def __call__(self, payload: P_contra) -> R_co: ...


def dispose(proposal: Proposal[P], disposer: Callable[[P], R]) -> Applied[R]:
    """Run the code-side disposer on a proposal inside a model-free region.

    Accepts any callable; Disposer is the named interface for class-based
    disposers. (Annotated as Callable because mypy cannot infer R through
    a generic Protocol parameter.)
    """
    with model_calls_forbidden(f"disposing proposal from {proposal.origin!r}"):
        result = disposer(proposal.payload)
    return Applied(result, _MINT_TOKEN)
