#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Working memory: what it is, and unifying its compaction story

Status: **converged** — compaction is **context assembly**, not a working-memory
cache. `spec.working_memory.compaction` writes `spec.context_manager` when that
slot is omitted. The summarising plugin's hysteresis is the cache (reuse summary
until history grows 20%). Authoritative:
[context-assembly.md](../manifests/context-assembly.md),
[agent.md](../manifests/agent.md), [plugin-bindings.md](../manifests/plugin-bindings.md).

File:line references below are historical and will drift.


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
   `note_agent_response()` copies whatever is sitting in the in-flight buffer
   into `committed_messages` *before* clearing the in-flight buffer, then
   applies the context manager's recency cap so the stored log cannot grow
   without bound.

So the full picture the manifest author should have in mind: system prompt
(`injected_context`, rebuilt fresh from the manifest every time — never
accumulates) + `committed_messages` (the recency-capped record — recent
user turns, tool calls, tool results, and assistant replies) + whatever the
CURRENT turn has produced so far but not yet committed.
`assemble_llm_messages()` stitches exactly these three pieces into the
message list sent to the LLM, in that order.

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

   The assembler plugin calls `cm.manage_history(past, budget_hint)` on
   **every single turn**, where `past` is committed history and `budget_hint`
   is the model context window minus completion reserve (overridable via
   `spec.context_manager.params.trimmer`). See [context-assembly.md](../manifests/context-assembly.md)
   for assembly-time token trim (tool-group-aware, pin-tail on the live WM round).

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

`SummarizingConversation` used to raise if `summarize_fn` was `None`. It is now
optional: a `drop` summarizer (or `llm` with no live engine) keeps the last
`keep_turns` user turns verbatim and discards older ones.

## Resolution (implemented)

**One config surface: `spec.context_manager`.** `spec.working_memory.compaction`
is sugar that writes that slot. Compaction policy is `manage_history`. The
LLM view is bounded at assemble time. After each turn commit the same recency
cap is written back to the committed log (folded prefix dropped). The cache
for in-turn LLM calls is **hysteresis on the context-manager instance**.

1. **`working_memory.compaction`** translates to `context_manager`:

   ```yaml
   working_memory:
     persistent: true
     compaction:
       strategy: keep_recent   # keep_recent | sliding_window | summarize
       max_messages: 200       # keep_recent → stack
       window_size: 20         # sliding_window
       summary_threshold: 0    # summarize — 0 uses model context_window − reserve
       keep_turns: 10          # summarize — recent user turns kept verbatim
   ```

   Mapping: `keep_recent → stack`, `sliding_window → sliding_window`,
   `summarize → summarising`. Prefer writing `spec.context_manager` directly;
   if both are set, `context_manager` wins.

2. **Summarizer sub-plugins** (registry type `summarizer`): `llm` (default)
   uses the agent's engine via `CMFactory.create(..., engine=ctx.engine)`.
   Optional `params.model` (a `spec.models[].id` or LiteLLM string) uses a
   different model for the summary call. Optional `params.instructions`
   replaces the package system prompt (the **trigger** is still the token
   budget). `drop` discards older turns. The engine is **not** stored in the
   spec. See [summarization.md](../manifests/summarization.md). Example:
   [summarizer-override](../../library-standard/examples/context/summarizer-override/).

3. **Package default** when both slots are omitted: `context_manager:
   summarising` with `summarizer: llm` (see [plugin-bindings.md](../manifests/plugin-bindings.md)).
   That is not unbounded stack history.

4. **`spec.memory.compaction` deleted** — it was never wired.

Tests: `library-standard/tests/test_working_memory_compaction.py` (facade
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
