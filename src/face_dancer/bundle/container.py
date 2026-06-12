import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ValidationError

from face_dancer.bundle.errors import BundleError, BundleVersionError
from face_dancer.bundle.version import BUNDLE_SCHEMA_VERSION
from face_dancer.sheet import Sheet
from face_dancer.state import DynamicState


class Bundle(BaseModel):
    character_id: UUID = Field(default_factory=uuid4)
    name: str
    bundle_version: int = BUNDLE_SCHEMA_VERSION
    sheet: Sheet = Field(default_factory=Sheet)
    state: DynamicState = Field(default_factory=DynamicState)
    rider: dict[str, Any] = Field(default_factory=dict)

    def serialize(self) -> str:
        """Return the JSON representation of this bundle."""
        return self.model_dump_json(indent=2)

    @classmethod
    def deserialize(cls, raw: str) -> "Bundle":
        """Parse and validate a raw JSON string into a Bundle.

        Raises ``BundleError`` on malformed JSON or validation failure,
        and ``BundleVersionError`` if the version is mismatched.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BundleError(f"malformed JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise BundleError(f"expected a bundle object, got {type(data).__name__}")

        try:
            bundle = cls.model_validate(data)
        except ValidationError as exc:
            raise BundleError(f"invalid bundle: {exc}") from exc

        if bundle.bundle_version != BUNDLE_SCHEMA_VERSION:
            raise BundleVersionError(
                f"bundle_version {bundle.bundle_version} != current {BUNDLE_SCHEMA_VERSION}"
            )

        return bundle

    @classmethod
    def load(cls, path: Path) -> "Bundle":
        """Load a bundle from the given file path."""
        return cls.deserialize(path.read_text())

    def unload(self, path: Path) -> None:
        """Persist this bundle to the given file path."""
        path.write_text(self.serialize() + "\n")
