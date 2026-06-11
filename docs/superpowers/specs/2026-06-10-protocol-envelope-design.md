# Protocol Envelope, Versioning & Message-Type Union

**Issue:** [#9](https://github.com/GeorgeLautenschlager/face-dancer/issues/9)
**Date:** 2026-06-10
**Status:** Approved

## Purpose

The wire protocol is the contract between a Face Dancer character and whatever
host it plugs into. Brief §3/§5: the wire protocol is structured data (JSON); the
markdown/YAML a model reads is a *render* of that data, regenerated each turn,
never the source of truth and never parsed back. The vocabulary is **closed and
versioned** — a new op or message shape is a schema-version bump, not an ad-hoc
field.

This issue defines the protocol's skeleton: a common message **envelope**, the
discriminated **union** of the six message types, a single **validation
entrypoint**, and the one defined place a schema-version bump happens. It does
*not* define the rich internals of each body (the closed effect-op vocabulary,
structured rider effects, dice math) — those belong to the rider and resolution
issues that own them. Here the bodies are thin.

Three deliverables:

1. An **envelope + discriminated union** of `propose_delta`, `apply_delta`,
   `contest`, `intent`, `request_roll`, `roll_result`, each round-tripping
   validate → serialize → parse.
2. A single **validation entrypoint** and a single, defined schema-version
   change point.
3. A **JSON Schema export** of the union — the artifact a non-Python host
   implements against without reading our code.

## Decisions

- **Pydantic v2, isolated to the protocol package** — this is a versioned wire
  contract third parties implement against, the one place in the codebase a
  validation library earns its keep. Pydantic gives discriminated-union dispatch,
  clear parse errors, and free JSON-Schema export. It is a *leaf* dependency:
  only `face_dancer.protocol` imports it; the membrane and everything else stay
  stdlib-only. Chosen over hand-rolled dataclasses (we'd hand-maintain a separate
  schema document and risk sync drift) and msgspec (obscure; perf isn't the
  binding constraint for tiny turn-based messages).
- **Thin bodies** — model the envelope, the six-type union, and the minimal
  fields each body obviously needs. The closed effect-op vocabulary and rich
  delta/claim/roll structures are deferred to the rider/resolution issues that
  own them, so #9 doesn't pre-empt vocabulary decisions assigned elsewhere.
- **Four envelope fields** — `type` (discriminator), `schema_version`,
  `message_id` (unique per message, for logging/dedup/traceability), and
  `correlation_id` (groups one resolution exchange). `turn_id` is deferred until a
  subsystem (decision/perception) actually needs turn grouping — it would be a
  guessed field today.
- **Strict version rejection** — `validate()` rejects any message whose
  `schema_version != SCHEMA_VERSION` with a loud `SchemaVersionError`. Hosts must
  speak the same closed version; silently accepting a drifting version is exactly
  the bug the "closed and versioned" decision exists to prevent. Chosen over a
  lenient "accept older, warn" policy.
- **One change point** — `SCHEMA_VERSION` is a single constant in `version.py`,
  and the union is built from one `MESSAGE_TYPES` tuple in `messages.py`. Adding a
  message type is two co-located edits (append the class to `MESSAGE_TYPES`; bump
  `SCHEMA_VERSION` if the wire contract changed). Nothing elsewhere names message
  types by hand.
- **JSON Schema export is in scope** — nearly free with pydantic, and it pays off
  the brief's host-agnostic constraint directly: the published schema is the
  contract, so a host implements the protocol without seeing the character's
  internals.

## Architecture

The protocol lives under the existing `src/face_dancer/protocol/` stub. Pydantic
v2 is added to `[project].dependencies` in `pyproject.toml`.

```
src/face_dancer/protocol/
├── __init__.py      # re-exports the public API
├── version.py       # SCHEMA_VERSION + the documented bump procedure
├── envelope.py      # Envelope base model (the four common fields)
├── messages.py      # the 6 message classes + the MESSAGE_TYPES union registry
├── validation.py    # validate() + export_schema()
└── errors.py        # ProtocolError, SchemaVersionError, UnknownMessageType
```

Dependency direction: `envelope.py` imports `version.py` (for the
`schema_version` default); `messages.py` imports `envelope.py`; `validation.py`
imports `messages.py`, `version.py`, and `errors.py`. No cycles.

## The envelope (`envelope.py`)

Every message subclasses a common base carrying the four chosen fields:

```python
class Envelope(BaseModel):
    type: str                            # overridden per-class as a Literal discriminator
    schema_version: int = SCHEMA_VERSION  # validate() rejects any other value
    message_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
```

`message_id` defaults to a fresh UUID so callers constructing outbound messages
needn't supply one. `correlation_id` is required: the propose → contest → roll →
apply chain shares it, and an `intent` mints a new one to open an outbound
exchange. `schema_version` defaults to `SCHEMA_VERSION` so outbound construction
is ergonomic; strictness lives in `validate()`, which rejects any *inbound*
message whose `schema_version` differs from `SCHEMA_VERSION` (see below). The
default's only effect is that a message omitting the field is treated as the
current version.

## The version change point (`version.py`)

```python
SCHEMA_VERSION = 1   # the one line a version bump touches
```

A module docstring documents the bump procedure: to add a message type, append
its class to `MESSAGE_TYPES` in `messages.py`; bump `SCHEMA_VERSION` here only if
the change alters the wire contract a host already speaks. This is the single,
defined change point the issue's definition-of-done requires.

`schema_version` is a monotonic integer, not semver — the wire field only needs
to answer "do we speak the same version?", and an integer compares trivially.

## The message union (`messages.py`)

Each message is a `BaseModel` subclass of `Envelope` with a `Literal` `type` tag
and a thin body. Richer internals are deferred to the issues that own them.

| Message | Direction | Thin body |
|---|---|---|
| `propose_delta` | session → char | `target: str`, `tags: frozenset[str]`, `effects: list[dict]` *(effect-op shape owned by resolution)* |
| `apply_delta` | session → char | `target: str`, `tags: frozenset[str]`, `effects: list[dict]`; authoritative; shares `correlation_id` with the propose it finalizes |
| `contest` | char → session | `claims: list[str]` *(claims, not verdicts — prose; structured effects deferred to rider)* |
| `intent` | char → session | `action: str` *(prose; opens a new exchange/correlation_id)* |
| `request_roll` | session → char | `kind: str` (e.g. `"saving_throw"`), `dc: int \| None` |
| `roll_result` | char → session | `natural: int`, `modifier: int`, `total: int` *(wire shape; the roll itself is computed in code in the resolution issue)* |

The union and its registry, co-located:

```python
MESSAGE_TYPES = (ProposeDelta, ApplyDelta, Contest, Intent, RequestRoll, RollResult)
Message = Annotated[Union[MESSAGE_TYPES], Field(discriminator="type")]
```

`effects: list[dict]` is deliberately open. The resolution issue will replace
`dict` with the typed closed effect-op union; until then the protocol carries the
shape without asserting it, so #9 doesn't pre-empt that vocabulary.

## Validation & serialization (`validation.py`)

One public entrypoint:

```python
def validate(raw: dict | str) -> Message:
    """Parse and validate a raw message into its concrete typed form.

    Dispatches on `type` via the discriminated union, then enforces
    schema_version. Raises a ProtocolError on any failure.
    """
```

Behaviour:

- Accepts a `dict` or a JSON `str`.
- Dispatches on the `type` discriminator through a `TypeAdapter(Message)`.
- An unknown `type` raises `UnknownMessageType`.
- A `schema_version` other than `SCHEMA_VERSION` raises `SchemaVersionError`.
- Any other pydantic `ValidationError` is wrapped so callers catch one
  `ProtocolError` family.

Serialization is pydantic-native: `msg.model_dump_json()` / `msg.model_dump()`.
The round-trip property `validate(m.model_dump()) == m` holds for every message
type and is tested per type.

Schema export:

```python
def export_schema() -> dict:
    """Return the JSON Schema for the full message union."""
    return TypeAdapter(Message).json_schema()
```

A small `python -m face_dancer.protocol.validation` (or equivalent script entry)
writes the schema to `docs/protocol/schema.json` so the published contract can be
regenerated and committed.

## Error handling (`errors.py`)

```python
class ProtocolError(Exception): ...          # base — callers catch this family
class SchemaVersionError(ProtocolError): ...  # schema_version != SCHEMA_VERSION
class UnknownMessageType(ProtocolError): ...  # discriminator matches no member
```

These signal a malformed or mis-versioned message at the boundary; the validation
entrypoint is the one place that raises them. Pydantic's internal
`ValidationError` for a structurally invalid body is wrapped into a
`ProtocolError` so consumers depend on the protocol package's own exception
surface, not pydantic's.

## Testing

Plain pytest units in `tests/test_protocol/`:

1. Round-trip per message type: `validate(m.model_dump()) == m` and
   `validate(m.model_dump_json()) == m` for all six.
2. Unknown `type` raises `UnknownMessageType`.
3. Wrong `schema_version` raises `SchemaVersionError`.
4. Envelope defaults: a constructed message gets a fresh `message_id`; two
   constructions differ.
5. `export_schema()` returns a schema whose discriminator mapping names all six
   message types.
6. The existing import smoke test (`tests/test_hello.py`) still passes.

All code passes `mypy --strict` and the existing ruff config.

## Out of scope

- The closed effect-op vocabulary (`reduce`, `scale`, `negate`, …) and structured
  delta operations — the resolution issue; `effects` stays `list[dict]` here.
- Structured rider claims/effects on `contest` — the rider issue; `claims` is
  `list[str]` here.
- Dice mechanics and modifier math behind `request_roll` / `roll_result` — the
  resolution issue; the protocol carries only the wire numbers.
- `turn_id` and any turn-grouping — deferred until a subsystem needs it.
- Specializing the membrane `Proposal`/`Applied` seam (issue #8) over these
  concrete shapes — a later integration; #9 defines the data, not the seam
  binding.
