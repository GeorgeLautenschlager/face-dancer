"""Smoke test — verifies the package is importable and submodules are present."""

import importlib

SUBMODULES = [
    "face_dancer",
    "face_dancer.protocol",
    "face_dancer.bundle",
    "face_dancer.membrane",
    "face_dancer.state",
    "face_dancer.rider",
    "face_dancer.resolution",
    "face_dancer.decision",
    "face_dancer.perception",
    "face_dancer.hosts",
]


def test_all_submodules_importable() -> None:
    for name in SUBMODULES:
        mod = importlib.import_module(name)
        assert mod is not None, f"could not import {name}"
