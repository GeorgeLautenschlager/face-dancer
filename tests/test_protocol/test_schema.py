"""Tests for the published JSON-Schema export of the message union."""

from face_dancer.protocol.validation import export_schema


def test_schema_names_all_six_discriminators() -> None:
    schema = export_schema()
    text = repr(schema)
    for tag in (
        "propose_delta",
        "apply_delta",
        "contest",
        "intent",
        "request_roll",
        "roll_result",
    ):
        assert tag in text, f"schema is missing discriminator {tag!r}"


def test_schema_is_a_mapping_with_discriminator() -> None:
    schema = export_schema()
    assert isinstance(schema, dict)
    # Pydantic emits a `discriminator` mapping for a tagged union.
    assert "discriminator" in repr(schema)
