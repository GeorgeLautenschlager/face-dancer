# Spike: Backing Store for Dynamic State — JSON blob vs SQLite + history

**Issue:** [#2](https://github.com/GeorgeLautenschlager/face-dancer/issues/2)
**Date:** 2026-06-11
**Status:** Approved — decision recorded
**Type:** Spike (time-boxed, decision-producing) · brief §7 open question

## Question

What backs the authoritative dynamic-state store (current HP, conditions,
resources, position) — a single **JSON blob**, or a **SQLite row plus a history
table** that enables turn-N replay/debugging?

## Decision

**JSON blob.** Dynamic state is a JSON-serializable object persisted as the
`state` artifact slot of the character bundle. There is no separate database and
no turn-history table in v0. SQLite + a history table is the documented upgrade
path, taken only if and when turn-N replay/debugging becomes a real requirement.

## Rationale

- **Consistency with the bundle decision ([#10](https://github.com/GeorgeLautenschlager/face-dancer/issues/10)).**
  A character persists as a *single* JSON file, and dynamic state is one of its
  three artifacts (the `state` slot, currently an opaque dict). Keeping state as a
  JSON object preserves "one portable file = one character." A SQLite store would
  be a sidecar `.db` file alongside the bundle, splitting the character across two
  files and breaking that portability.
- **Light dependencies / local-embeddable posture (brief §4).** The JSON blob
  adds nothing — `json` is stdlib and the bundle already (de)serializes through
  pydantic. SQLite would add a schema and a persistence layer the embeddable v0
  doesn't need.
- **Replay is not a v0 requirement (brief §8).** In-session learning and the
  memory consolidation loop are explicit non-goals; "v0 just needs the turn loop
  to run." Turn-N replay/debugging is the *only* thing the SQLite option buys over
  a blob, and it is a nice-to-have we can defer.
- **AC3 is already satisfied by the bundle round-trip.** "State is non-volatile
  across sessions: load → play → unload → reload yields identical state" is met by
  the bundle's existing `load`/`unload`/`serialize` (#10) — code writes state into
  the `state` dict, the bundle persists it, a reload restores it. No separate
  store is needed to satisfy non-volatility.
- **Code authors all writes (brief §5).** This holds under either store; the JSON
  blob does not weaken it. The dynamic-state module owns the in-memory state object
  and is the only writer; the LLM never mutates it. The blob is just where that
  object rests between sessions.

## What this means for the dynamic-state issue

The dynamic-state issue (schema + persistence) builds on this decision:

- Dynamic state is a **JSON-serializable, code-owned object** that occupies the
  bundle's `state` slot. Its concrete schema (HP, conditions, resources, position)
  is that issue's to define — this spike only fixes the *backing store*, not the
  shape.
- **Persistence is the bundle's persistence.** State is written/read as part of
  `Bundle.unload` / `Bundle.load`; the dynamic-state module does not own its own
  file or connection. When the `state` slot is given a typed model (replacing the
  opaque dict), it must remain JSON-round-trippable so the single-file bundle
  contract holds.
- **No turn history.** State is the *current* snapshot only; prior turns are not
  retained. A turn that supersedes a value overwrites it.

## Upgrade path (if replay is later wanted)

The decision is reversible at the persistence layer because state is an opaque
slot in the bundle. If turn-N replay/debugging becomes a real need, the migration
is additive: introduce a sidecar SQLite store *beside* the bundle holding an
append-only history, leaving the bundle's `state` slot as the authoritative
current snapshot. A starter history-table shape for that future work:

```
state_history(
    character_id   TEXT,     -- the bundle's character_id
    turn           INTEGER,  -- monotonic turn counter
    state_json     TEXT,     -- the full state snapshot after the turn
    correlation_id TEXT,     -- the apply_delta that produced it
    applied_at     TEXT      -- ISO timestamp
)
```

**What would trigger reconsidering:** a concrete need for turn-by-turn replay or
post-hoc debugging of "why did state become X on turn N," or state growing past
what fits comfortably in a single JSON file. Absent one of those, the blob stands.

## Out of scope

- The dynamic-state **schema** itself (HP/conditions/resources/position shape) —
  the dynamic-state issue.
- Memory stores (episodic → semantic → procedural) — a separate brief; deferred.
- Building the SQLite store — only sketched here as the documented upgrade path;
  not implemented.
