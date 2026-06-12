"""Construction, round-trip, persistence, and error tests for the Bundle container."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from face_dancer.bundle.container import Bundle
from face_dancer.bundle.errors import BundleError, BundleVersionError
from face_dancer.bundle.version import BUNDLE_SCHEMA_VERSION
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState


@pytest.mark.parametrize("name", ["Test Character", "Another One"])
def test_construction(name: str) -> None:
    bundle = Bundle(name=name)

    assert bundle.name == name
    assert isinstance(bundle.character_id, UUID)
    assert bundle.bundle_version == BUNDLE_SCHEMA_VERSION
    assert bundle.sheet == Sheet()
    assert bundle.state == DynamicState()
    assert bundle.rider == {}

    # Ensure different bundles get different IDs
    bundle2 = Bundle(name=name)
    assert bundle.character_id != bundle2.character_id


def test_construction_with_values() -> None:
    char_id = uuid4()
    name = "Test Character"
    sheet = {"stats": {"strength": 10}}
    state = {"hp": 50}
    rider = {"rules": "no dice"}

    bundle = Bundle(
        character_id=char_id,
        name=name,
        sheet=sheet,
        state=state,
        rider=rider,
    )

    assert bundle.character_id == char_id
    assert bundle.name == name
    assert bundle.sheet == Sheet(stats={"strength": 10})
    assert bundle.state == DynamicState(hp=50)
    assert bundle.rider == rider


def test_round_trip_empty() -> None:
    original = Bundle(name="Empty")
    serialized = original.serialize()
    rebuilt = Bundle.deserialize(serialized)

    assert rebuilt == original


def test_round_trip_populated() -> None:
    original = Bundle(
        name="Populated",
        sheet={"stats": {"attr": 1}},
        state={"hp": 7, "conditions": ["prone"]},
        rider={"rule": 3},
    )
    serialized = original.serialize()
    rebuilt = Bundle.deserialize(serialized)

    assert rebuilt == original


def test_load_unload_reload(tmp_path: Path) -> None:
    original = Bundle(name="Persistence Test", sheet={"stats": {"a": 1}})
    path = tmp_path / "char.json"

    # unload (persist)
    original.unload(path)
    assert path.exists()

    # on-disk format is a pretty-printed JSON file with a trailing newline
    written = path.read_text()
    assert written.endswith("\n")
    assert "\n  " in written  # indent=2 pretty-printing

    # load
    reloaded = Bundle.load(path)
    assert reloaded == original

    # reload again (idempotency check)
    reloaded.unload(path)
    reloaded2 = Bundle.load(path)
    assert reloaded2 == original
    assert reloaded2 == reloaded


def test_deserialize_version_error() -> None:
    # Create JSON with wrong version
    bad_json = '{"name": "Bad Version", "bundle_version": 999}'
    with pytest.raises(BundleVersionError):
        Bundle.deserialize(bad_json)


def test_deserialize_errors() -> None:
    # Malformed JSON
    with pytest.raises(BundleError):
        Bundle.deserialize("{ invalid json")

    # Missing required field 'name'
    missing_name = '{"character_id": "00000000-0000-0000-0000-000000000000"}'
    with pytest.raises(BundleError):
        Bundle.deserialize(missing_name)

    # Not a dictionary
    with pytest.raises(BundleError):
        Bundle.deserialize("[]")


def test_state_survives_load_play_unload_reload(tmp_path: Path) -> None:
    # AC3: load -> play (code mutates state) -> unload -> reload yields identical state.
    bundle = Bundle(name="Fighter")
    bundle.state.hp = 18
    bundle.state.conditions.add("prone")
    bundle.state.resources["second_wind"] = 1

    path = tmp_path / "char.json"
    bundle.unload(path)
    reloaded = Bundle.load(path)

    assert reloaded.state == bundle.state
    assert reloaded.state.hp == 18
    assert "prone" in reloaded.state.conditions
    assert reloaded.state.resources["second_wind"] == 1
