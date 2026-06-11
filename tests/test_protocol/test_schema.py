"""Tests for the published JSON-Schema export of the message union."""

import json
from pathlib import Path

from face_dancer.protocol.validation import export_schema

EXPECTED_DISCRIMINATORS = {
    "propose_delta",
    "apply_delta",
    "contest",
    "intent",
    "request_roll",
    "roll_result",
}

# The committed published contract, relative to the repo root (pytest's working dir).
SCHEMA_PATH = Path("docs/protocol/schema.json")


def test_schema_discriminator_mapping_names_all_six() -> None:
    schema = export_schema()
    mapping = schema["discriminator"]["mapping"]
    assert set(mapping) == EXPECTED_DISCRIMINATORS


def test_schema_is_a_tagged_union_over_six_members() -> None:
    schema = export_schema()
    assert isinstance(schema, dict)
    assert schema["discriminator"]["propertyName"] == "type"
    assert len(schema["oneOf"]) == 6


def test_committed_schema_matches_export() -> None:
    # Drift guard: the committed artifact must equal a fresh export. If this fails,
    # regenerate with `python3 -m face_dancer.protocol.validation` and commit.
    committed = json.loads(SCHEMA_PATH.read_text())
    assert committed == export_schema()
