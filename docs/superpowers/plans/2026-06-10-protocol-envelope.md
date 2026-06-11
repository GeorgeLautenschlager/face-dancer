# Protocol Envelope, Versioning & Message-Type Union Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:local-subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Face Dancer wire-protocol skeleton — a common message envelope, a discriminated union of the six message types, a single strict validation entrypoint, a single schema-version change point, and a JSON-Schema export of the union.

**Architecture:** Pydantic v2 models under `src/face_dancer/protocol/`, isolated as the only package that imports pydantic. Every message subclasses a shared `Envelope`; the six concrete types form a pydantic discriminated union keyed on a `type` literal. A single `validate()` entrypoint dispatches on that discriminator and strictly rejects any non-current `schema_version`. The union doubles as the single registry — `MESSAGE_TYPES` is derived from it — and `export_schema()` emits the published contract.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, ruff, mypy (`--strict`).

**Spec:** `docs/superpowers/specs/2026-06-10-protocol-envelope-design.md`

---

## File Structure

```
src/face_dancer/protocol/
├── __init__.py      # MODIFY: re-export the public API (keep existing docstring)
├── version.py       # CREATE: SCHEMA_VERSION + documented bump procedure
├── envelope.py      # CREATE: Envelope base model (four common fields)
├── messages.py      # CREATE: 6 message classes; Message union; MESSAGE_TYPES (derived)
├── validation.py    # CREATE: validate(), export_schema(), write_schema(), __main__
└── errors.py        # CREATE: ProtocolError, SchemaVersionError, UnknownMessageType

tests/test_protocol/
├── __init__.py        # CREATE
├── test_messages.py   # CREATE: round-trip + envelope defaults
├── test_validation.py # CREATE: validate() dispatch, strict version, unknown type
└── test_schema.py     # CREATE: export_schema() contains all six discriminators

docs/protocol/schema.json   # CREATE: generated, committed
pyproject.toml              # MODIFY: add pydantic to dependencies
```

**Implementation note on the single registry:** the spec describes a `MESSAGE_TYPES`
tuple that `Message` is built from. For `mypy --strict` to understand the union,
`Message` must be a static type alias — it cannot be built from a runtime tuple.
So we invert: `Message` (the static `Annotated[Union[...], discriminator]`) is the
one place message types are listed, and `MESSAGE_TYPES` is *derived* from it via
`typing.get_args`. This preserves the spec's intent (one defined place to add a
message type — the `Message` alias) while keeping mypy happy.

---

## Task 1: Add pydantic dependency and install the package

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pydantic to runtime dependencies**

In `pyproject.toml`, change the dependencies line under `[project]`:

```toml
dependencies = ["pydantic>=2"]
```

- [ ] **Step 2: Install the package with dev extras (also installs mypy/ruff/pytest)**

Run: `python3 -m pip install -e ".[dev]"`
Expected: installs `face-dancer` editable plus pydantic, pytest, pytest-cov, ruff, mypy.

- [ ] **Step 3: Verify the existing smoke test now passes**

Run: `pytest tests/test_hello.py -q`
Expected: PASS (the package is now importable).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pydantic v2 dependency (issue #9)"
```

---

## Task 2: Version constant and error hierarchy

**Files:**
- Create: `src/face_dancer/protocol/version.py`
- Create: `src/face_dancer/protocol/errors.py`
- Create: `tests/test_protocol/__init__.py`
- Test: `tests/test_protocol/test_validation.py` (started here; extended in Task 4)

- [ ] **Step 1: Write the failing test**

Create `tests/test_protocol/__init__.py` (empty file).

Create `tests/test_protocol/test_validation.py`:

```python
"""Tests for the protocol version constant and error hierarchy."""

from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.version import SCHEMA_VERSION


def test_schema_version_is_a_positive_int() -> None:
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


def test_error_hierarchy() -> None:
    assert issubclass(SchemaVersionError, ProtocolError)
    assert issubclass(UnknownMessageType, ProtocolError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_protocol/test_validation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'face_dancer.protocol.errors'`.

- [ ] **Step 3: Write version.py**

Create `src/face_dancer/protocol/version.py`:

```python
"""Schema version and the single change point for the wire protocol.

The wire vocabulary is closed and versioned. To add a message type, append its
class to the ``Message`` union in ``messages.py`` (the one defined place message
types are listed). Bump ``SCHEMA_VERSION`` below only when a change alters the
wire contract a host already speaks — adding an optional field a host can ignore
need not bump it; adding a required field or a new message type the host must
understand does.

The version is a monotonic integer, not semver: the wire field only needs to
answer "do we speak the same version?", which an integer compares trivially.
"""

SCHEMA_VERSION = 1
```

- [ ] **Step 4: Write errors.py**

Create `src/face_dancer/protocol/errors.py`:

```python
"""Protocol boundary errors.

Raised only by the validation entrypoint. Callers catch the ``ProtocolError``
family rather than pydantic's own ``ValidationError``.
"""


class ProtocolError(Exception):
    """Base class for all protocol validation failures."""


class SchemaVersionError(ProtocolError):
    """A message's schema_version did not match the current SCHEMA_VERSION."""


class UnknownMessageType(ProtocolError):
    """A message's `type` discriminator matched no known message type."""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_protocol/test_validation.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/protocol/version.py src/face_dancer/protocol/errors.py tests/test_protocol/__init__.py tests/test_protocol/test_validation.py
git commit -m "feat(protocol): add schema version constant and error hierarchy (issue #9)"
```

---

## Task 3: Envelope and the six message types

**Files:**
- Create: `src/face_dancer/protocol/envelope.py`
- Create: `src/face_dancer/protocol/messages.py`
- Test: `tests/test_protocol/test_messages.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_protocol/test_messages.py`:

```python
"""Round-trip and envelope-default tests for the six message types."""

from uuid import UUID, uuid4

import pytest

from face_dancer.protocol.messages import (
    MESSAGE_TYPES,
    ApplyDelta,
    Contest,
    Intent,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.protocol.version import SCHEMA_VERSION


def _one_of_each() -> list:
    cid = uuid4()
    return [
        ProposeDelta(correlation_id=cid, target="self", tags=frozenset({"fire"}),
                     effects=[{"op": "reduce", "amount": 8}]),
        ApplyDelta(correlation_id=cid, target="self", tags=frozenset({"fire"}),
                   effects=[{"op": "reduce", "amount": 4}]),
        Contest(correlation_id=cid, claims=["I have fire resistance and a save"]),
        Intent(correlation_id=uuid4(), action="I drink the potion"),
        RequestRoll(correlation_id=cid, kind="saving_throw", dc=15),
        RollResult(correlation_id=cid, natural=12, modifier=3, total=15),
    ]


@pytest.mark.parametrize("msg", _one_of_each())
def test_round_trip_through_python(msg) -> None:
    rebuilt = type(msg).model_validate(msg.model_dump())
    assert rebuilt == msg


@pytest.mark.parametrize("msg", _one_of_each())
def test_round_trip_through_json(msg) -> None:
    rebuilt = type(msg).model_validate_json(msg.model_dump_json())
    assert rebuilt == msg


def test_message_id_defaults_to_unique_uuid() -> None:
    a = Intent(correlation_id=uuid4(), action="wave")
    b = Intent(correlation_id=uuid4(), action="wave")
    assert isinstance(a.message_id, UUID)
    assert a.message_id != b.message_id


def test_schema_version_defaults_to_current() -> None:
    msg = Intent(correlation_id=uuid4(), action="wave")
    assert msg.schema_version == SCHEMA_VERSION


def test_message_types_registry_has_all_six() -> None:
    assert set(MESSAGE_TYPES) == {
        ProposeDelta, ApplyDelta, Contest, Intent, RequestRoll, RollResult
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_protocol/test_messages.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'face_dancer.protocol.messages'`.

- [ ] **Step 3: Write envelope.py**

Create `src/face_dancer/protocol/envelope.py`:

```python
"""The common message envelope shared by every wire message."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from face_dancer.protocol.version import SCHEMA_VERSION


class Envelope(BaseModel):
    """Fields every protocol message carries.

    ``type`` is overridden in each concrete subclass as a ``Literal`` so it can
    serve as the discriminated-union tag. ``schema_version`` defaults to the
    current version for ergonomic outbound construction; strictness lives in
    ``validate()``, which rejects any inbound mismatch.
    """

    type: str
    schema_version: int = SCHEMA_VERSION
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
```

- [ ] **Step 4: Write messages.py**

Create `src/face_dancer/protocol/messages.py`:

```python
"""The six wire message types and their discriminated union.

The ``Message`` alias is the single place message types are listed. Adding a
type means adding its class and listing it in ``Message``; ``MESSAGE_TYPES`` is
derived from the union so it can never drift.
"""

from typing import Annotated, Any, Literal, get_args

from pydantic import Field

from face_dancer.protocol.envelope import Envelope


class ProposeDelta(Envelope):
    """Session-proposed change, not yet committed (session -> character)."""

    type: Literal["propose_delta"] = "propose_delta"
    target: str
    tags: frozenset[str] = frozenset()
    effects: list[dict[str, Any]] = Field(default_factory=list)


class ApplyDelta(Envelope):
    """Authoritative change the character's code applies (session -> character).

    Shares ``correlation_id`` with the ``propose_delta`` it finalizes.
    """

    type: Literal["apply_delta"] = "apply_delta"
    target: str
    tags: frozenset[str] = frozenset()
    effects: list[dict[str, Any]] = Field(default_factory=list)


class Contest(Envelope):
    """Character-surfaced claims, not verdicts (character -> session)."""

    type: Literal["contest"] = "contest"
    claims: list[str] = Field(default_factory=list)


class Intent(Envelope):
    """Character-side opener; the session adjudicates it into a propose_delta."""

    type: Literal["intent"] = "intent"
    action: str


class RequestRoll(Envelope):
    """A save or check to resolve (session -> character). DC is session-owned."""

    type: Literal["request_roll"] = "request_roll"
    kind: str
    dc: int | None = None


class RollResult(Envelope):
    """A rolled result; total == natural + modifier, computed in code elsewhere."""

    type: Literal["roll_result"] = "roll_result"
    natural: int
    modifier: int
    total: int


Message = Annotated[
    ProposeDelta | ApplyDelta | Contest | Intent | RequestRoll | RollResult,
    Field(discriminator="type"),
]

# Derived from the union above so the two can never drift. get_args(Message)
# unwraps the Annotated to (<union>, FieldInfo); get_args on that union yields
# the member classes.
MESSAGE_TYPES: tuple[type[Envelope], ...] = get_args(get_args(Message)[0])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_protocol/test_messages.py -q`
Expected: PASS (14 passed — 6 + 6 parametrized round-trips plus 2 default tests... count may vary; all green).

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/protocol/envelope.py src/face_dancer/protocol/messages.py tests/test_protocol/test_messages.py
git commit -m "feat(protocol): add envelope and the six message-type union (issue #9)"
```

---

## Task 4: The strict validation entrypoint

**Files:**
- Create: `src/face_dancer/protocol/validation.py`
- Test: `tests/test_protocol/test_validation.py` (extend the file from Task 2)

- [ ] **Step 1: Replace the test file with the full version**

Replace the **entire** contents of `tests/test_protocol/test_validation.py` (the
Task 2 version had only the version/error tests; this adds the imports at the top
and the `validate()` tests — ruff's `E402`/`I` rules forbid mid-file imports, so
the import block must stay at the top):

```python
"""Tests for the protocol version, error hierarchy, and validate() entrypoint."""

from uuid import uuid4

import pytest

from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.messages import Intent, ProposeDelta
from face_dancer.protocol.validation import validate
from face_dancer.protocol.version import SCHEMA_VERSION


def test_schema_version_is_a_positive_int() -> None:
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


def test_error_hierarchy() -> None:
    assert issubclass(SchemaVersionError, ProtocolError)
    assert issubclass(UnknownMessageType, ProtocolError)


def test_validate_dispatches_on_discriminator() -> None:
    msg = ProposeDelta(correlation_id=uuid4(), target="self")
    parsed = validate(msg.model_dump())
    assert isinstance(parsed, ProposeDelta)
    assert parsed == msg


def test_validate_accepts_json_string() -> None:
    msg = Intent(correlation_id=uuid4(), action="wave")
    parsed = validate(msg.model_dump_json())
    assert isinstance(parsed, Intent)
    assert parsed == msg


def test_validate_rejects_unknown_type() -> None:
    raw = {"type": "teleport", "correlation_id": str(uuid4())}
    with pytest.raises(UnknownMessageType):
        validate(raw)


def test_validate_rejects_wrong_schema_version() -> None:
    raw = {
        "type": "intent",
        "schema_version": SCHEMA_VERSION + 1,
        "correlation_id": str(uuid4()),
        "action": "wave",
    }
    with pytest.raises(SchemaVersionError):
        validate(raw)


def test_validate_wraps_bad_body_as_protocol_error() -> None:
    # `intent` requires an `action`; omitting it is a body error, not a version
    # or discriminator error.
    raw = {"type": "intent", "correlation_id": str(uuid4())}
    with pytest.raises(ProtocolError):
        validate(raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_protocol/test_validation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'face_dancer.protocol.validation'`.

- [ ] **Step 3: Write validation.py**

Create `src/face_dancer/protocol/validation.py`:

```python
"""The single validation entrypoint and JSON-Schema export for the protocol."""

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.messages import MESSAGE_TYPES, Message
from face_dancer.protocol.version import SCHEMA_VERSION

_adapter: TypeAdapter[Message] = TypeAdapter(Message)
_VALID_TYPES: frozenset[str] = frozenset(
    m.model_fields["type"].default for m in MESSAGE_TYPES
)


def validate(raw: dict[str, Any] | str) -> Message:
    """Parse and validate a raw message into its concrete typed form.

    Dispatches on the ``type`` discriminator, then enforces ``schema_version``.
    Raises a ``ProtocolError`` subclass on any failure: ``UnknownMessageType``
    for an unrecognised discriminator, ``SchemaVersionError`` for a version
    mismatch, and ``ProtocolError`` for a structurally invalid body.
    """
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ProtocolError(f"expected a message object, got {type(data).__name__}")

    type_tag = data.get("type")
    if type_tag not in _VALID_TYPES:
        raise UnknownMessageType(f"unknown message type: {type_tag!r}")

    try:
        msg = _adapter.validate_python(data)
    except ValidationError as exc:
        raise ProtocolError(f"invalid {type_tag} message: {exc}") from exc

    if msg.schema_version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"schema_version {msg.schema_version} != current {SCHEMA_VERSION}"
        )
    return msg


def export_schema() -> dict[str, Any]:
    """Return the JSON Schema for the full message union — the published contract."""
    return _adapter.json_schema()


def write_schema(path: Path) -> None:
    """Write the JSON Schema to ``path`` (creating parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export_schema(), indent=2) + "\n")


if __name__ == "__main__":
    write_schema(Path("docs/protocol/schema.json"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_protocol/test_validation.py -q`
Expected: PASS (all version, error-hierarchy, and validate tests green).

- [ ] **Step 5: Commit**

```bash
git add src/face_dancer/protocol/validation.py tests/test_protocol/test_validation.py
git commit -m "feat(protocol): add strict validate() entrypoint (issue #9)"
```

---

## Task 5: JSON-Schema export and generated contract file

**Files:**
- Create: `tests/test_protocol/test_schema.py`
- Create: `docs/protocol/schema.json` (generated)

- [ ] **Step 1: Write the failing test**

Create `tests/test_protocol/test_schema.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails (or passes if Task 4 already imported cleanly)**

Run: `pytest tests/test_protocol/test_schema.py -q`
Expected: PASS — `export_schema()` already exists from Task 4. (This task locks the schema behaviour with a test and generates the committed artifact. If the import fails, revisit Task 4.)

- [ ] **Step 3: Generate the schema file**

Run: `python3 -m face_dancer.protocol.validation`
Expected: creates `docs/protocol/schema.json`.

- [ ] **Step 4: Sanity-check the generated file**

Run: `python3 -c "import json; d=json.load(open('docs/protocol/schema.json')); print('propose_delta' in json.dumps(d))"`
Expected: prints `True`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_protocol/test_schema.py docs/protocol/schema.json
git commit -m "feat(protocol): export published JSON Schema of the message union (issue #9)"
```

---

## Task 6: Public API re-exports and final quality gate

**Files:**
- Modify: `src/face_dancer/protocol/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_protocol/test_messages.py`:

```python
def test_public_api_is_reexported() -> None:
    import face_dancer.protocol as protocol

    for name in (
        "Message",
        "Envelope",
        "ProposeDelta",
        "ApplyDelta",
        "Contest",
        "Intent",
        "RequestRoll",
        "RollResult",
        "MESSAGE_TYPES",
        "SCHEMA_VERSION",
        "validate",
        "export_schema",
        "ProtocolError",
        "SchemaVersionError",
        "UnknownMessageType",
    ):
        assert hasattr(protocol, name), f"protocol package does not re-export {name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_protocol/test_messages.py::test_public_api_is_reexported -q`
Expected: FAIL with `AssertionError: protocol package does not re-export Message`.

- [ ] **Step 3: Update __init__.py (keep the existing module docstring)**

Replace the contents of `src/face_dancer/protocol/__init__.py` with — keeping the original docstring at the top:

```python
"""Wire protocol — structured JSON message shapes for the character ↔ host contract.

Messages: propose_delta, contest, apply_delta, intent, request_roll, roll_result.
Markdown/YAML are renders of this data, never the source of truth.
"""

from face_dancer.protocol.envelope import Envelope
from face_dancer.protocol.errors import (
    ProtocolError,
    SchemaVersionError,
    UnknownMessageType,
)
from face_dancer.protocol.messages import (
    MESSAGE_TYPES,
    ApplyDelta,
    Contest,
    Intent,
    Message,
    ProposeDelta,
    RequestRoll,
    RollResult,
)
from face_dancer.protocol.validation import export_schema, validate
from face_dancer.protocol.version import SCHEMA_VERSION

__all__ = [
    "MESSAGE_TYPES",
    "SCHEMA_VERSION",
    "ApplyDelta",
    "Contest",
    "Envelope",
    "Intent",
    "Message",
    "ProposeDelta",
    "ProtocolError",
    "RequestRoll",
    "RollResult",
    "SchemaVersionError",
    "UnknownMessageType",
    "export_schema",
    "validate",
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_protocol/test_messages.py::test_public_api_is_reexported -q`
Expected: PASS.

- [ ] **Step 5: Run the full quality gate**

Run each and confirm all pass:

```bash
pytest
ruff check src tests
ruff format --check src tests
mypy
```

Expected:
- `pytest`: all tests pass (protocol suite + existing smoke test).
- `ruff check`: no errors.
- `ruff format --check`: no files would be reformatted. (If it reports diffs, run `ruff format src tests` and re-stage.)
- `mypy`: `Success: no issues found` (config has `strict = true`, `files = ["src"]`).

- [ ] **Step 6: Commit**

```bash
git add src/face_dancer/protocol/__init__.py tests/test_protocol/test_messages.py
git commit -m "feat(protocol): re-export public API and pass full quality gate (issue #9)"
```

---

## Definition of Done (from the issue)

- [x] Every message type round-trips validate → serialize → parse — Task 3 (round-trip tests) + Task 4 (`validate()`).
- [x] The schema version is a single, defined change point — Task 2 (`SCHEMA_VERSION` in `version.py`) + Task 3 (the `Message` alias as the single message-type list).
- [x] A single validation entrypoint — Task 4 (`validate()`).
- [x] Strict version rejection — Task 4 (`SchemaVersionError`).
- [x] Published contract for host-agnostic implementers — Task 5 (`export_schema()` + `docs/protocol/schema.json`).

## Notes for the executor

- `mypy` is **not** in CI (CI runs ruff + pytest only), but the project's convention
  (see the membrane spec) is that all code passes `mypy --strict`. Run it locally as
  part of Task 6's gate.
- Do not specialize the membrane `Proposal`/`Applied` seam over these shapes — that
  is a later integration issue, explicitly out of scope here.
- Keep `effects: list[dict[str, Any]]` open; the resolution issue replaces it with
  the typed closed effect-op union later.
