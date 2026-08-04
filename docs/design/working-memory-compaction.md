#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Working memory: what it is, and unifying its compaction story

Status: **implemented** on `feat/persistent-working-memory`
(`spec.working_memory.persistent` and `spec.working_memory.compaction` both
shipped — see `docs/manifests/agent.md` §Working memory across delegate
calls). File:line references are current as of writing and will drift —
treat them as pointers, not guarantees.

## What "working memory" actually is (one buffer, two phases)

There is one accumulating conversation buffer per agent, not two. It's easiest
to describe as two phases of a single pipeline, not two separate memories:

1. **In-flight (uncommitted) phase** — `WorkingMemoryStore`
   (`runtime/src/mas/runtime/boundary/context/working_memory.py`). While a
   turn's ReAct loop is still running, every tool call and tool result the
   LLM produces THIS turn is appended here, because the model needs to see
   its own not-yet-committed tool trajectory before the turn concludes.
2. **Committed phase** — `AutoCtxAssembler.committed_messages`/`turn_history`
   (`runtime/src/mas/runtime/driver/mocks.py`). At the end of every turn,
   `note_agent_response()` (`mocks.py:80-103`) copies whatever is sitting in
   the in-flight buffer into `committed_messages` (`self.working_memory.
   messages` → `self.committed_messages.extend(...)`, `mocks.py:86-87`)
   *before* clearing the in-flight buffer. Nothing is discarded at turn end —
   it's relocated.

So the full picture the manifest author should have in mind: system prompt
(`injected_context`, rebuilt fresh from the manifest every time — never
accumulates) + `committed_messages` (the permanent, growing record — system
prompt, then every turn's user input, tool calls, tool results, and assistant
replies, all folded in) + whatever the CURRENT turn has produced so far but
not yet committed. `assemble_llm_messages()` (`runtime/src/mas/runtime/
boundary/context/assemble.py:52-104`) stitches exactly these three pieces
into the message list sent to the LLM, in that order.

`spec.working_memory.persistent` governs the committed phase only — it's
what a delegated agent falls back on across separate `delegate_to_<agent>`
calls, keyed by `(session_id or context_id, agent_id)` in
`WorkingMemoryRegistry` (`runtime/src/mas/runtime/boundary/context/
working_memory_registry.py`).

The in-flight phase used to have one real gap: `_finalize_turn`
(`ctl/src/mas/ctl/session/controller.py`) only folded the in-flight buffer
into `committed_messages` when the turn wasn't paused for HITL — so a
delegated turn paused mid-flight (e.g. an approval gate on a tool call) lost
its already-executed tool calls the moment the *next* turn's
`note_user_input()` cleared working memory. Fixed: `_finalize_turn` now
folds in whenever there's a response and/or working memory to fold,
regardless of `awaiting_hitl`; checkpointing still only happens for a turn
that actually completed. See
`ctl/tests/test_session_controller_finalize_turn.py`.

## The tension: two overlapping, non-identical compaction surfaces

`docs/schemas/runtime/agent.schema.yaml` currently has two places that both
claim to control how much history is kept:

1. **`spec.context_manager.params`** — `max_turns`/`window_size`,
   `max_messages`, `summary_threshold`, `keep_turns`
   (`docs/schemas/runtime/fragments/context-manager-params.schema.yaml`).
   This one is real: `CMFactory.create(manifest=manifest)` (`runtime/src/mas/
   runtime/contracts/cm_factory.py`) resolves it via the plugin registry to
   one of three working, tested strategies in `library-standard/src/mas/
   library/standard/plugins/context/conversation.py`:
   - `StackConversation` — cap total messages.
   - `SlidingWindowConversation` — cap by turn-pair count.
   - `SummarizingConversation` — compress older turns into a summary system
     block, keep the last N verbatim.

   `assemble_llm_messages()` calls `cm.manage_history(past, max_tokens)`
   (`assemble.py:78-80`) on **every single turn**, where `past` is exactly
   `ctx.committed_messages` — so compaction already applies for free to
   persisted/registry-restored working memory, with zero extra code, the
   moment a manifest sets `context_manager: {type: <one of the above>}`.

2. **`spec.memory.compaction`** (was `agent.schema.yaml` lines ~261-305) — a
   richer, schema-only surface: `strategy: keep_recent|summarize|
   chunked_summarize`, `keep_recent_ratio`, `min_chunk_ratio`,
   `safety_margin`, `identifier_preservation`, `summarize_instructions`.
   **Nothing in the codebase read this.** Repo-wide grep for
   `chunked_summarize`/any consumer of `spec.memory.compaction` returned
   nothing outside the schema file itself. Aspirational schema, no
   implementation behind it. **Removed** (see Resolution below).

Two schema surfaces claiming the same job, only one of which did anything,
was exactly the kind of drift `BRANCHES.md`/`docs/design/flavour-boundary.md`
already calls out for other subsystems (see "What the code already gets
right" there for the pattern this doc follows).

## The other dead end (fixed): `SummarizingConversation` was unusable

`SummarizingConversation.__init__` (`conversation.py`) raised `ValueError` if
`summarize_fn` was `None`, and it defaulted to `None`. A repo-wide grep for
`summarize_fn` turned up exactly one place it was *consumed* (inside
`conversation.py` itself) and zero places it was *supplied* — no production
call site, no test. `mas.cm.summarising` was registered and selectable via
`context_manager: {type: summarising}`, but selecting it raised immediately.
Also fixed in passing: its `threshold_tokens` constructor param didn't match
the schema's own `summary_threshold` field name (never caught, since nothing
ever constructed it) — renamed to match.

## Resolution (implemented)

**One config surface, exposed where the manifest author actually looks for
it — `spec.working_memory.compaction` — backed entirely by the existing,
already-tested `context_manager`/`CMFactory` machinery. No new engine.**

1. **`working_memory.compaction`** added to `agent.schema.yaml` (sibling of
   `working_memory.persistent`):

   ```yaml
   working_memory:
     persistent: true
     compaction:
       strategy: keep_recent   # keep_recent (default) | sliding_window | summarize
       max_messages: 200       # keep_recent
       window_size: 20         # sliding_window
       summary_threshold: 4000 # summarize
       keep_turns: 10          # summarize
   ```

   `runtime/src/mas/runtime/boundary/context/working_memory_compaction.py`
   translates this into the existing `context_manager` binding shape
   (`{"type": ..., "params": {...}}`) via a strategy → plugin-type table
   (`keep_recent → stack`, `sliding_window → sliding_window`,
   `summarize → summarising`) and hands it to the same
   `CMFactory.create()` already wired at `assemble.py:78`. Pure facade:
   `StackConversation`, `SlidingWindowConversation`, and
   `SummarizingConversation` are reused verbatim, not rewritten.

   `spec.context_manager` set directly still works and takes precedence —
   `working_memory.compaction` is sugar over it, not a replacement.
   `instantiate_runtime()` (`ctl/src/mas/ctl/session/bootstrap.py`) calls
   `apply_working_memory_compaction(spec, engine=selection.engine)` right
   after the engine is resolved, and mirrors the result onto
   `options.agent_manifest["spec"]["context_manager"]` too (the dict
   `LiveLlmEngine` holds a live reference to and re-reads every turn).

2. **`spec.memory.compaction` deleted** from the schema — no implementation,
   no test coverage, no callers. Pure subtraction.

3. **`summarize` strategy is now real.** `build_llm_summarize_fn(engine)`
   builds a `summarize_fn` backed by the agent's own resolved engine, reusing
   `LiveLlmEngine`'s existing completion primitives
   (`_model_access_chat`/`_chat_completion`) rather than the full
   `InvokeEngineIo`/kernel turn machinery (this is a one-off, out-of-band
   call during context assembly, not a tracked turn). If the resolved engine
   doesn't look live (no completion primitives — e.g. a bare
   `SimulatedEngine`), compaction degrades to `keep_recent` with a warning
   instead of crashing at first use.

4. **Sensible default: no LLM round-trip unless asked for.**
   `strategy: keep_recent` stays the default when `working_memory.compaction`
   is omitted entirely (unbounded history, matching prior behavior) — never
   spends a model call just to manage history size. `summarize` is opt-in.

Tests: `runtime/tests/integration/test_working_memory_compaction.py` (facade
translation + `build_llm_summarize_fn` + real `CMFactory` instantiation),
`ctl/tests/test_working_memory_compaction_bootstrap.py` (end-to-end through
`instantiate_runtime()`).

## Non-goals

- Cross-process/restart-persisted working memory (`spec.memory.persistence`)
  — separate follow-up, not blocked by this.
- Compacting the semantic/episodic retrieval-store memory layers
  (`spec.memory.types[]`) — unrelated subsystem (`MemoryContract`), already
  has its own (different) lifecycle.
- `chunked_summarize`, `identifier_preservation`, `safety_margin` from the
  old `memory.compaction` shape — no evidence of demand beyond the
  unimplemented schema; add if/when a concrete need shows up, not
  speculatively.
