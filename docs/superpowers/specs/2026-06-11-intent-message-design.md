# Intent Message — Character-Side Opener

**Issue:** [#13](https://github.com/GeorgeLautenschlager/face-dancer/issues/13)
**Date:** 2026-06-11
**Status:** Approved

## Purpose

Brief §3 — the outbound arc opens with an `intent` ("I drink the potion"). The
session validates legality and adjudicates it *into* a `propose_delta`, which
then resolves through the identical inbound path. **Capability is
character-known; affordance (what's legal now) is session-known** — so the
character proposes and the session validates; the character never enumerates its
own legal moves.

Issue #9 stood `intent` up as a thin placeholder (`action: str`). This issue
gives it the real schema: a machine-readable action/target the session
adjudicates, plus an optional expressive narration, carrying **no assertion of
legality**.

## Decisions

- **`Intent` carries `action`, `target`, and `narration`** — a simple
  host-understood action reference, an optional named target, and an optional
  in-character flair string. Example: `action="cast fireball"`,
  `target="goblin"`, `narration="With only the barest hint of contempt, Melian
  hurls a fireball at the goblin."`

- **`action` and `target` are the machine contract; `narration` is the
  expressive layer** — `action`/`target` are simple, host-understood references
  the session reads and adjudicates. `narration` is room for the agent to play
  the role; the session may render/display it but **never parses it for mechanics
  or legality**. This keeps flavor strictly out of adjudication and mirrors the
  brief's tactical (action/target) vs. expressive (narration) decision split.
  Chosen over a `parameters` dict: capability-specific args, if ever needed, are
  the capability interface's (#22) concern; for v0 a simple action + target
  covers the case and narration carries the roleplay.

- **No assertion of legality (the DoD)** — holds by construction: there is no
  `valid` / `legal` / `dc` / legality field, and `target` is a *name*, not a
  validated reference. The character names what it perceives and proposes; the
  session owns whether it is legal.

- **The capability reference stays open** — `action` is a plain `str`. The
  capability *schema* (the "action interface") is issue
  [#22](https://github.com/GeorgeLautenschlager/face-dancer/issues/22); #13 does
  not define it. Mirrors how #11 kept `Delta.payload` open pending its owner.

- **`target` and `narration` are optional (`str | None = None`)** — an intent may
  be targetless (`"I take cover"`) or flair-free (`action="cast fireball"`
  alone). `action` is required.

- **`SCHEMA_VERSION` stays `1`; regenerate `docs/protocol/schema.json`** — adding
  two optional, defaulted fields is backward-compatible (existing `action`-only
  intents still validate), so no version bump (version.py policy: "adding an
  optional field a host can ignore need not bump it"). The committed schema
  artifact is regenerated; the drift guard enforces it.

## Architecture

`Intent` is a message in the union, so it stays inline in `messages.py` (its body
is expanded; it is not reused as a standalone model the way `Delta` is). No new
module. The `Message` union, `MESSAGE_TYPES`, and the other five message types
are untouched.

```
src/face_dancer/protocol/
└── messages.py     # Intent body: action + target + narration
docs/protocol/
└── schema.json     # regenerated
```

## The `Intent` message (`messages.py`)

```python
class Intent(Envelope):
    """Character-side opener; the session adjudicates it into a propose_delta.

    ``action`` and ``target`` are the simple, host-understood contract the session
    reads and adjudicates; the character names a target but never asserts its
    legality (affordance is session-owned). ``narration`` is optional in-character
    flair the session may render but never parses for mechanics.
    """

    type: Literal["intent"] = "intent"
    action: str
    target: str | None = None
    narration: str | None = None
```

## Testing

Extend `tests/test_protocol/`:

1. **Round-trip:** an action-only `Intent` and a full `Intent` (action + target +
   narration) each satisfy `validate(m.model_dump()) == m` and the JSON variant.
2. **`action` required:** a raw `intent` missing `action` raises `ProtocolError`
   from `validate()`.
3. **Defaults:** `Intent(correlation_id=..., action="x")` has `target is None` and
   `narration is None`.
4. **Field-set drift guard:** `Intent.model_fields` keys are exactly
   `{type, schema_version, message_id, correlation_id, action, target,
   narration}` — so no legality field can be added without a deliberate test
   edit. This is the "carries no assertion of legality" guarantee in test form.
5. **Schema:** regenerate `docs/protocol/schema.json`; the `test_schema.py`
   assertions (six-member tagged union, discriminator mapping, committed ==
   export) pass.

Existing `action`-only `Intent` fixtures in `test_messages.py` /
`test_validation.py` keep working unchanged (the new fields are optional). All
code passes `mypy --strict` and the existing ruff config.

## Out of scope

- The **capability schema / action interface** — issue #22 (`action` stays an
  open string here).
- **Perception / target resolution** — issue #21; `target` is a bare name #13
  neither resolves nor validates.
- **Session-side adjudication** of an intent into a `propose_delta` — the
  resolution spine's concern, not the message schema.
- A `parameters` field for capability args — deferred to #22 if a capability
  needs it.
- A `SCHEMA_VERSION` bump.
