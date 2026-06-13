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
                if e.perceivable_with <= scope.tags and (e.check is None or self._resolve(e.check))
            ],
        )
