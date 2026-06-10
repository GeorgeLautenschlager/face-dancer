"""Smoke test: the membrane's public API is importable from the package root."""

from face_dancer import membrane


def test_public_api_names_resolve() -> None:
    assert membrane.__all__, "membrane must declare a public API"
    for name in membrane.__all__:
        assert hasattr(membrane, name), f"missing public name: {name}"
