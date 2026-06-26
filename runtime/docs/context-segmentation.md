<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Context segmentation

How prompt context is assembled, provenance-tracked, and reflected in
`events.jsonl` traces.

---

## Layers

| Layer | Holds | Persistence |
|-------|-------|-------------|
| **L1 — Transcript** | User/assistant turns visible to the model | Session + trace |
| **L2 — Stores** | Memory, RAG, skills (via `ContextContract`) | Backend-dependent |
| **L3 — DP state** | Design-pattern phase (plan/act/synth, tool queue) | `QProduct.dp_data` |

The kernel assembles L1+L2 into the messages array for each `LLM_CALL`. L3
influences scheduling via `evaluate_next` / `handle_event`, not as raw transcript
unless the DP injects instruction parts.

---

## ContextPart and provenance

Each contributor returns `ContextPart` values with:

- **role** — system, user-facing instruction, tool catalog facet, etc.
- **mechanism** — `inject`, `rag`, `tool_call`, `dp_instruction`, …
- **provenance** — source plugin, segment id, optional budget weight

The assembler merges parts, applies `ContextManagerContract.manage_history`,
then enforces token budget eviction (drop lowest-priority segments first).

---

## Trace events

Context assembly emits observability events consumed by bench pipelines:

| Event kind | Meaning |
|------------|---------|
| `context_assembled` | Final messages + segment list for one LLM call |
| `llm_call_start` / `llm_call_end` | Model egress interval |
| `tool_call_start` / `tool_call_end` | Tool egress interval |

Segments in `context_assembled` align with provenance ids so paper figures
(`extract_trace_stats`, lifecycle moodbars) can attribute context to plugins.

See [trajectory-schema.md](trajectory-schema.md) for the full schema.

---

## Post-tool context

After a tool returns, the kernel may run a **post-tool collect** pass so memory
and DP plugins append results before the next `LLM_CALL`. Mechanism is tagged
`tool_call` in provenance for attribution.

---

## Budget eviction

When estimated tokens exceed the manifest budget:

1. Trim history via context manager (summarize or drop oldest turns).
2. Drop optional context parts by priority (skills before system policy).
3. Fail closed with a governance event if required parts cannot fit.

Configure budgets in manifest `spec.context` and governance policies.

---

## Related docs

- [dev/contracts/state-and-context.md](dev/contracts/state-and-context.md)
- [automaton-product-model.md](automaton-product-model.md) §6, §26
- [mealy-envelope.md](mealy-envelope.md) — context assembly order in checklist
