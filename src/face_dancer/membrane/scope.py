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
