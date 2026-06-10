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
