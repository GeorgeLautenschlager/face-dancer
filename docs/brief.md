---
title: "Face Dancer: Portable Character Agent"
slug: face-dancer
repo: https://github.com/GeorgeLautenschlager/face-dancer
status: ready to implement
created: 2026-06-05
summary: A self-owning RPG/game character agent that holds its own authoritative state and mechanical self-knowledge, acts credibly as an opponent or companion, and drops into any host (game engine, DM agent, or human-run session) over a small portable protocol.
---

## 1. Problem

There is no *portable* character. The card-frontend world (SillyTavern, RisuAI, Agnai) gives you a character that can talk but not act, and that owns no authoritative state. The DM-agent world bakes the character into the session, so it dies when the session does and can't travel to a different host. OpenClaw can express a character but stuffs everything into the system prompt — far too heavy to run a credible character on a small, embeddable, open-weight model. Nobody has the unit we actually want: a lightweight character that owns itself, acts with some competence, carries the rules that are true of it, and can be dropped into a video game, another agent's RPG session, or a human's Discord campaign without any of them being experts on it.

## 2. Outcome

A character is a durable, self-contained bundle you bring to a game — the way a player brings a sheet to a table. It holds and persists its own state and its own mechanical self-knowledge. It perceives a scene the host describes to it, decides what to do, and proposes actions; the host adjudicates and tells it what happened; the character records the result. It plays credibly as an opponent or a companion, and it does so on a local model fast enough to participate in turn-based games. The same character bundle can be used in many different games — with no changes to the character.

## 3. Approach

The character is a self-owning unit that closes one loop with whatever host it's plugged into. The host (a "session controller" — game engine, DM agent, or human) owns world state and final adjudication; the character owns itself.

**The character carries three artifacts.** A *sheet* (static identity and stats — ability scores, max HP, AC, modifiers, proficiencies). A *dynamic state* store (volatile, authoritative, code-written — current HP, conditions, resources, position). A *rules-rider* (reactive, character-known mechanics a host can't be assumed to know — resistances, special saves, homebrew clauses). Static stats live on the sheet; *proactive* capabilities ("I can cast Fireball") live in the action interface; the rider holds only *reactive* rules ("when fire is done to me, here's a rule you may not know"). That fence keeps the rider from becoming a second sheet.

This document uses the Dungeons & Dragons 5E system for consistency in examples. However, this is not baked into the structure of the artifacts above. A 5e character built for this agent is portable into any other 5e game, and the same is true of any ruleset for authoring characters.

**One resolution loop, two directions.** World-acts-on-character and character-acts-on-world resolve through the same spine:

- Inbound: the session sends a `propose_delta` (proposed, not applied). If a rider clause matches, the character replies with a `contest` carrying *claims* (not verdicts). A save or check may resolve via a `request_roll` / `roll_result` pair. The session re-adjudicates and sends a final, authoritative `apply_delta`. The character's *code* applies it to dynamic state.
- Outbound: the character emits an `intent` ("I drink the potion"). The session validates legality and adjudicates it *into* a `propose_delta`, which then resolves through the identical inbound path.

So actions need no separate machinery — they reuse `propose → contest? → apply`. The verbs are three load-bearing ones (`propose_delta`, `contest`, `apply_delta`) plus `intent` as the character-side opener and the roll pair as an optional resolution rider.

**The opponent half is the proactive arc of that loop.** Perception (session → character, epistemically scoped to what this character can know) feeds a decision step. The decision step is split: *tactical* choices (targeting, move selection) run at a faster pace than *expressive* choices (speech, social and moral beats). The initial approach is to route *both* to the LLM and target turn based games first. The chosen action leaves as an `intent`. Capability ("what I can do") is character-known; affordance ("what's legal right now") is session-known, so the character proposes and the session validates rather than the character enumerating its own legal moves. Goals bias the decision at three timescales: persistent drives (from persona), situational objectives (scene-level, often supplied by the host), tactical intent (per turn).

**The membrane is the same everywhere.** Character owns/knows X, session owns/knows Y; the model proposes and code disposes; an epistemic scope filter sits between them. Rider, perception, capability, and decision policy are four instances of that one pattern.

The wire protocol is structured data (JSON). The markdown/YAML a model reads is a *render* of that data, regenerated each turn — never the source of truth and never parsed back.

## 4. Constraints

- **Deployment envelope:** embeddable with an open-weight quant (at time of writing Qwen 3.6 / Gemma 4 class). The architecture must be context-frugal and retrieval-first. This is the constraint that *forces* the design, not one to engineer around.
- **Model placement:** the LLM must stay off the critical path for state mutation and arithmetic. Code authors every write; code does every roll and calculation. This code is made available to the model for deterministic tool calls, where appropriate.
- **Host-agnostic:** the same character must run against a game engine, an LLM DM, and a human over Discord. No host may be assumed to know the character's rules, and a host must be able to implement the protocol without seeing the character's internals.
- **Dependency posture:** prefer light dependencies; this is explicitly *not* a rebuild of a heavy framework. New deps need a reason.
- **Locality:** local/embeddable posture; no assumption of cloud services.

## 5. Decisions made

- **Character owns and persists its own state** — portability; a character whose state is subsumed by the session can't leave the session.
- **Ownership ≠ authority** — the character stores the sheet but the session has authority over what happens to it; the character honors adjudicated deltas, it doesn't negotiate them. Mirrors the table; keeps the unreliable small model from adjudicating its own fate. The agent has exactly one recourse and that's to contest a proposed delta with a clearly applicable entry from its rules rider. Even in this case, the session proposes the new delta, not the agent.
- **Code authors all writes; the LLM never mutates state or does arithmetic** — the small model is the least reliable component; letting it own the authoritative numbers reintroduces exactly the "silently cheats / heals itself" failure we're removing.
- **Wire protocol is structured data; markdown/YAML is a render of it** — data is truth, view is disposable; a small model burns fewer tokens and makes fewer errors reading a clean render than authoring a state blob.
- **One resolution loop for both world-caused and self-caused change** — `intent` adjudicates into a `propose_delta` and resolves through the same `propose → contest? → apply` spine; no second subsystem for actions.
- **Two-phase propose/apply** — a delta is proposed before it commits, so the character can contest before the write. Cannot be retrofitted onto a single-shot apply.
- **`contest` carries claims, not verdicts** — the character surfaces rules it knows ("I have fire resistance and a save"), the session still adjudicates and owns the final number. Shared interpretation without ceding authority.
- **The portable character carries a rules-rider distinct from sheet and action interface** — rider = reactive character-known mechanics a host may not know; sheet = static stats; action interface = proactive capabilities. Bounds the rider so it doesn't grow into a second sheet.
- **Rider clauses are tagged `mechanical` or `judgment`** — mechanical clauses auto-contest in code; judgment clauses route their one question to a mind. Keeps the scarce model out of routine rules bookkeeping.
- **Rider triggers match on op + tag-set (all tags present)** — one mechanic ("anything fire") spans damage, conditions, and saves without enumerating event shapes; the matcher is a set comparison reusing the protocol's tag vocabulary, not a parser.
- **Effect-op vocabulary is closed and versioned** — starter ops: `reduce`, `scale`, `negate`, `grant_save`, `modify_roll`, `replace`. A new op is a schema-version bump. Pressure to add conditionals inside an effect is the signal that clause should be `judgment`, not a richer op — this is what stops the rider becoming a rules engine.
- **Every rider clause has a mandatory `claim` string plus optional structured `effect`** — progressive enhancement; a structured host mechanizes the effect, a dumb/prose host reads the claim and adjudicates by hand. Same rider, both worlds.
- **Rider clauses carry per-clause `source` provenance** — auditability; provenance is precisely what fine-tuning destroys, and here it survives.
- **`order` on a rider is a proposal, not a verdict** — the character declares its understanding of resolution sequence; the session can override.
- **Perception is session → character and epistemically scoped** — the character only perceives what it could plausibly know; the host's sole obligation is to describe the perceivable scene in a standard shape.
- **Capability is character-known; affordance (legality now) is session-known** — the character proposes intent, the session validates; the character never enumerates its own legal moves.
- **OpenClaw is reference, not base** — its memory systems are worth studying, but its everything-in-the-system-prompt approach is the anti-pattern this project exists to avoid.

## 6. Rejected alternatives

- **Session owns the sheet / state subsumed by the game** — kills portability; the character can't survive leaving the session.
- **LLM authors the writes or does the arithmetic** — puts authoritative state on the critical path of the flakiest component; produces self-healing / silently-cheating bugs.
- **Markdown or free text as the source of truth for dynamic state** — a small model drops fields and fumbles math when rewriting a state block. Acceptable only as a no-engine v0 compromise, never as the target.
- **Single-phase `apply_delta` with no proposal step** — can't be contested; locks out shared rule interpretation entirely.
- **`contest` returning verdicts ("therefore 14")** — cedes adjudication authority to the character; breaks the ownership ≠ authority line.
- **Rider as a general rules engine (conditionals inside effects)** — that case is a `judgment` clause; the op vocabulary stays closed.
- **Character enumerates its own legal actions** — that's session-owned affordance; leads to desync and the character asserting illegal moves.
- **Routing the inbound delta through the LLM so it decides whether to fire the tool (the "option 1" approach)** — kept only as a degraded fallback for prose-only hosts. The structured interface is the contract; prose parsing is a courtesy.

## 7. Open questions

- [x] Project name and repo are not chosen. — *(resolve: needs George)*
- [ ] Backing store for dynamic state: single JSON blob vs SQLite row plus a history table for turn-N replay/debugging. — *(resolve: in-repo; SQLite only if replay is wanted)*
- [ ] Starter tag vocabulary (damage types, condition names) and the closed effect-op set's exact initial members. — *(resolve: in-repo / spike; align with the first host's rule system)*
- [ ] DC-ownership edge cases in `request_roll`: session always supplies the DC, but can a rider ever assert one, and how is that reconciled? — *(resolve: needs a spike)*
- [ ] How a `judgment` clause reaches a mind when the host is dumb: does the character's own model adjudicate it, or does it punt the question to the host? — *(resolve: needs George / spike)*
- [ ] Where situational objectives come from when the host doesn't supply them (inferred by the character vs left empty). — *(resolve: in-repo)*

## 8. Non-goals

- **Memory write-back lifecycle / in-session learning** — the episodic → semantic → procedural consolidation loop is named and deferred to its own brief. v0 just needs the turn loop to run.
- **The model adapter** (OpenAI-compatible shuttle for OpenRouter / LM Studio / Ollama) — deferred; when built it stays dumb, knowing nothing about characters or memory.
- **Character Card V2/V3 and lorebook ingestion** — deferred; the portable bundle is defined here, the card-import bridge comes later.
- **The session/host itself** — we build the character's side of the contract, plus mock hosts for testing. We are not building the DM or the game.
- **The context assembler** (budget-aware per-turn selection across stores) — flagged as the eventual keystone; deferred to its own brief. Everything here feeds it.
- **Multi-agent orchestration, a plugin system, a general tool registry** — explicit heavy-framework tar pits; out of scope for the lightweight core.
- **Full rules competence** — the agent knows only the rules true of *itself* that a host might not know, not all of D&D (or any system).
- **Model selection / quantization work** — local LLMs are progressing to fast to pin this here. Instead, this is built model-agnostic

## 9. Acceptance criteria

- [ ] Given a `propose_delta` tagged `fire` and a character whose rider holds a `mechanical` fire-reduction clause, the character emits a `contest` carrying that claim **without invoking the model**.
- [ ] Given an `apply_delta`, the character's persisted dynamic state reflects the change, and a re-read returns the updated values — and the write was authored by code, not the model.
- [ ] A character's state is non-volatile across sessions: load → play → unload → reload yields identical state.
- [ ] Given a `request_roll`, the character rolls using its own modifier (from the sheet/rider) and reports a result whose total equals natural roll + modifier, computed in code.
- [ ] The model is never invoked to apply a delta, perform arithmetic, or auto-contest a `mechanical` rider clause (verifiable by instrumentation showing no model call on those paths).
- [ ] Given a scoped perception payload that omits a hidden entity, none of the character's emitted intents reference that entity.
- [ ] Given two candidate tactical actions, the decision policy selects one via the code heuristic with no model call.
- [ ] A rider clause that has only a `claim` and no structured `effect` still surfaces in a `contest` as prose (progressive-enhancement fallback works).
- [ ] The same character bundle loads against two different mock hosts and plays a turn in each with no character-side changes (host-agnostic contract holds).
- [ ] A self-caused action (`intent` to use an item) and a world-caused effect (incoming damage) both resolve to a state change through the same `apply_delta` path.

## 10. Context & pointers

- **OpenClaw** — reference implementation. Study its memory systems and its SOUL.md / AGENTS.md conventions; treat its prompt-stuffing as the anti-pattern. There is prior art for a card → agent bundle bridge (a "sillytavern-cards" skill on ClawHub) worth looking at when card ingestion comes up later.
- **Feudal Carriers** — a target host (space carrier sim with a 4X layer); the video-game-opponent use case for this agent.
- **Deathwatch** — a long-running human-run campaign on Discord; the prose-only / "dumb host" target that the `claim` fallback and the degraded option-1 parser exist to serve.
- **SillyTavern World Info / lorebook + prompt assembly** — prior art for the deferred context assembler and for the Tavern Character Card V2/V3 spec the eventual ingestion will target. Note: world lore is normally a standalone lorebook; character-specific knowledge rides in the card. The epistemic filter reconciles the two at assembly time.
- **PEARLS Lab, "I Cast Detect Thoughts"** — academic prior art on theory-of-mind and epistemic scoping (DM-knows vs NPC-knows vs player-knows) in D&D; closest existing work to the long-game thesis.
- **Cross-cutting principle to preserve through decomposition:** every hard boundary in this design is the same boundary — character owns/knows X, session owns/knows Y, model proposes and code disposes, epistemic filter as the membrane. Rider, perception, capability, and decision policy should each read as an instance of that one pattern, not as independent subsystems.
