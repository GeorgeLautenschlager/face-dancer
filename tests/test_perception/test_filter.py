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
    result = PerceptionScopeFilter().filter(scene, Scope(subject="c", tags=frozenset({"sight"})))
    assert _names(result) == set()  # AC6: hidden entity omitted


def test_keeps_capability_gated_entity_when_scope_has_the_tag() -> None:
    scene = Scene(entities=[Entity(name="imp", perceivable_with=frozenset({"truesight"}))])
    result = PerceptionScopeFilter().filter(
        scene, Scope(subject="c", tags=frozenset({"sight", "truesight"}))
    )
    assert _names(result) == {"imp"}


def test_check_gated_entity_dropped_by_default_resolver() -> None:
    scene = Scene(entities=[Entity(name="trap", check=PerceptionCheck(kind="perception", dc=15))])
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
