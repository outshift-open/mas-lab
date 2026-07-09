<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Agent Automaton as a Product of Mealy Machines

**Status:** Normative architecture companion (design target + v0.1 map in §14)  
**Audience:** Runtime architects, contract implementers, manifest authors  

> **OSS note:** The shipped kernel uses `CMFactory` and `DesignPatternPlugin` under
> `runtime/src/mas/runtime/contracts/`. `DPFactory` / `DPPhaseMachine` naming in this
> document describes the formal design target; see [mealy-envelope.md](mealy-envelope.md)
> for the v0.1 implementation checklist.

**Companion docs:** [contracts/DESIGN_SPACE.md](contracts/DESIGN_SPACE.md) (10 dimensions),
[contracts/MANIFEST_MAPPING.md](contracts/MANIFEST_MAPPING.md) (manifest mapping),  
[mealy-envelope.md](mealy-envelope.md) (implementation checklist — **authoritative for v0.1**)

**Contents:** §1–15 core model · §16 contract registry · §17 DPPhaseMachine · §18 all DPs ·  
§19 multi-agent · §20 ReAct adapter · §21 hook equivalence · §22 envelope · §23 lab matrix ·  
§24 target kernel · §26 context memory layers · §27 tool dual-channel · §28 Plan-Execute vs ReAct ·  
§29 interaction matrix · §30 per-step lifecycle · §25 extended summary

---

## 1. What we are modeling

An **agent** is not a single state machine. It is a **composed automaton** built from:

1. **Orthogonal dimensions** that coexist for the whole session (infrastructure, capabilities, governance, observability).
2. **Context sources** that all produce the same artifact — `ContextPart` with `ContextProvenance` — but are reached through different **calling semantics** (including the **tool dual-channel**: prompt catalog vs execution API — §6.4, §27).
3. **Design patterns** (ReAct, CoT, Plan-Execute, …) that **schedule** which contract calls happen and in what order; ReAct is one instance, not the kernel. DPs are also **context providers** (`collect_context`); the assembler **tracks** what was assembled (§6.5, §26–§30).
4. **Contract-call envelopes** that wrap every side effect (LLM, tool, memory query, transport send) with governance before/after and observability throughout.

The runtime kernel should be a thin **orchestrator** that:

- Steps the product on input symbols.
- Executes impure I/O in `execute_fn` callbacks (preserving Mealy purity).
- Interprets outputs (especially from `DPMachine` and `ContextMachine`).
- Never hard-codes ReAct.

---

## 2. Mealy machine notation

Each sub-system is a **Mealy machine**

\[
M = (Q, \Sigma, \Gamma, \delta, \lambda, q_0)
\]

| Symbol | Meaning |
|--------|---------|
| \(Q\) | Finite state set |
| \(\Sigma\) | Input alphabet (global symbols + dimension-specific symbols) |
| \(\Gamma\) | Output alphabet (actions + `NO_OUTPUT`) |
| \(\delta: Q \times \Sigma \to Q\) | Transition (may be guarded by `TransitionContext`) |
| \(\lambda: Q \times \Sigma \to \Gamma\) | Output |
| \(q_0\) | Initial state |

**Guards** are predicates on `TransitionContext` (agent_id, messages, security annotations, pending tool name, etc.). The production composer is `GuardedProductComposer`: guards are evaluated at step time, not dropped at build time.

**Purity rule:** Mealy machines never perform I/O. Side effects live in `execute_fn` passed to `execute_contract_call()`. The product is notified of results via `{contract}_execute` symbols and `context.metadata["result"]`.

---

## 3. Composition operators

The full agent formula uses **four** composition forms. Only the first is a classical automata product; the others are control structure.

### 3.1 Synchronous parallel product (⊗)

**Definition.** Given machines \(M_1, \ldots, M_n\) with state sets \(Q_1, \ldots, Q_n\):

\[
M_1 \otimes \cdots \otimes M_n
\]

- **Product state:** \(q = (q_1, \ldots, q_n) \in Q_1 \times \cdots \times Q_n\)
- **Step:** On input \(\sigma \in \Sigma\), each component \(M_i\) that has an enabled transition on \(\sigma\) fires; others stay in \(q_i\) with output `NO_OUTPUT`.
- **Joint output:** multiset (or ordered list) of \((\text{id}_i, \lambda_i(q_i, \sigma))\).

**Interpretation:** Dimensions are **orthogonal**. Session state does not replace model state; governance instance A does not replace governance instance B.

**Runtime implementation:** `GuardedProductComposer` — \(O(n)\) per step, no state-space explosion.

**Offline verification:** `ProductMealyComposer` materialises \(Q_1 \times \cdots \times Q_n\) for model checking (guarded transitions under-approximated).

### 3.2 Family product (⊗ᵢ) — multiple equivalent plugins

When several plugins implement the **same role** and must **all** see every relevant symbol:

\[
M_{\text{gov}} = M_{\text{gov}_1} \otimes M_{\text{gov}_2} \otimes \cdots \otimes M_{\text{gov}_n}
\]
\[
M_{\text{obs}} = M_{\text{obs}_1} \otimes M_{\text{obs}_2} \otimes \cdots \otimes M_{\text{obs}_m}
\]

**Cardinality:** `governance` and `observability` are `MULTIPLE_INSTANCE` dimensions. Each instance is an independent Mealy machine registered as `governance_budget`, `governance_sandbox`, `observability_otel`, `observability_native`, etc.

**Semantics:**

- On `governance_authorize` and `governance_validate`, **every** governance machine steps. Any `ABORT_EXECUTION` / `DENY` aborts the call (`GovernanceError`).
- On **every** symbol in a contract-call envelope (all 7), **every** observability machine steps. Each logs in turn; they are **equivalent observers** — none is authoritative over the others; all see the full trace including governance decisions before and after execution.

This is still a product, not a pipeline: observers do not filter each other's input.

### 3.3 Tagged sum (coproduct ⊔) — exactly one active variant

When **exactly one** implementation is selected per agent configuration:

\[
M_{\text{DP}} \in \{\, M_{\text{ReAct}},\, M_{\text{CoT}},\, M_{\text{PlanExecute}},\, \ldots \,\}
\]

\[
M_{\text{CM}} \in \{\, M_{\text{stack}},\, M_{\text{sliding}},\, M_{\text{summarising}},\, \ldots \,\}
\]

**Not** a runtime product of all patterns — the manifest picks one DP plugin; `DPFactory` / `CMFactory` instantiate the variant.

Formally this is a **disjoint union** of state spaces with a tag bit. The product formula uses one tagged component:

\[
M_{\text{agent}} = \cdots \otimes M_{\text{DP}}^{(\text{react})} \otimes \cdots
\]

Switching pattern = re-instantiating the agent product with a different summand.

### 3.4 Sequential composition (∘) — micro-protocols

A **contract call** is not one product step. It is a **fixed word** over \(\Sigma\):

\[
\mathcal{E}_{\text{call}}(c) = \sigma_1 \circ \sigma_2 \circ \cdots \circ \sigma_7
\]

Implemented as `execute_contract_call(contract_type, operation, execute_fn)`:

| # | Symbol | Who fires | Purpose |
|---|--------|-----------|---------|
| 1 | `{c}_{op}_start` | Obs\* | Open span / announce call |
| 2 | `governance_authorize` | Gov\* + Obs\* | Authorize before side effect |
| 3 | `observability_pre_execute` | Obs\* | Snapshot pre-state |
| — | `execute_fn()` | **Kernel** | Actual I/O (outside product) |
| 4 | `{c}_{op}_execute` | Cap + Obs\* + DP | Notify product of result |
| 5 | `observability_post_execute` | Obs\* | Snapshot post-state |
| 6 | `governance_validate` | Gov\* + Obs\* | Validate after side effect |
| 7 | `{c}_{op}_end` | Obs\* | Close span |

\*All instances in the family product step.

**Governance** touches symbols **2 and 6 only** (authorize + validate).  
**Observability** touches **all 7** (including governance decisions on 2 and 6).  
**Capability** machine for \(c\) is logically active at symbol 4; impure work is in `execute_fn`.

Context assembly uses the same envelope pattern with `ctx_collect_*` and `cm_assemble_*` symbol triples (see §7).

### 3.5 Iteration (μ) — design pattern loop

The **turn loop** is not part of the product state. It is an **outer scheduler** driven by `DPMachine` outputs:

\[
\mu X.\; \text{step}(\text{iteration\_start}) \;;\; \mathcal{E}_{\text{ctx}} \;;\; \mathcal{E}_{\text{llm}} \;;\; (\text{branch}_{\text{tool}} \cdot \mathcal{E}_{\text{tool}} \cdot \mathcal{E}_{\text{ctx}}')^* \;;\; \text{step}(\text{iteration\_end}) \;;\; X
\]

- `DPMachine` emits: `THINK` (→ LLM), `ACT` (→ tool), `FINALIZE`, `WAIT_EVENT`, etc.
- ReAct is **one** fixed point of this scheduler; CoT may skip the tool branch; Plan-Execute inserts `PLAN` before `ACT`.

The kernel **must not** hard-code `if tool_calls`; it must interpret DP outputs.

---

## 4. Full agent formula

Combining §3.1–§3.5:

\[
\boxed{
M_{\text{agent}} =
M_{\text{transport}}^{\varnothing}
\otimes M_{\text{session}}
\otimes M_{\text{obs}}^{\otimes m}
\otimes M_{\text{ctx}}
\otimes M_{\text{DP}}^{(p)}
\otimes M_{\text{model}}
\otimes M_{\text{src}}^{\otimes k}
\otimes M_{\text{gov}}^{\otimes n}
\otimes M_{\text{coord}}^{\varnothing}
}
\]

| Factor | Required? | Notes |
|--------|-------------|-------|
| \(M_{\text{transport}}\) | Optional | Multi-agent messaging |
| \(M_{\text{session}}\) | Typical | History, checkpoint, `session_id` |
| \(M_{\text{obs}}^{\otimes m}\) | **≥1** | All observers equivalent |
| \(M_{\text{ctx}}\) | **Yes** | Assembler + manager (§7) |
| \(M_{\text{DP}}^{(p)}\) | **Yes** | One pattern \(p\) from sum |
| \(M_{\text{model}}\) | **Yes** | LLM / embeddings |
| \(M_{\text{src}}^{\otimes k}\) | **≥1** | Unified context sources (§6) |
| \(M_{\text{gov}}^{\otimes n}\) | **≥0** | Budget, sandbox, policy, … |
| \(M_{\text{coord}}\) | Optional | Delegation, fan-out |

**Superscript \(\varnothing\):** omitted when not configured.

**What is NOT a separate product factor:**

- `ToolMachine`, `MemoryMachine` as **capability** dimensions — folded into **context sources** (§6) when the semantic role is "query → ContextPart". They still use \(\mathcal{E}_{\text{call}}\) when executing.
- `TransformationMachine` — absorbed into \(M_{\text{ctx}}\) filtering phase (RBAC, truncation).
- `ContextManagerContract` — sub-phase of \(M_{\text{ctx}}\), not a peer product factor (§7).

---

## 5. Dimension roles (refined taxonomy)

### 5.1 Infrastructure

| Machine | Contract | Role |
|---------|----------|------|
| Transport | `TransportContract` | Deliver inter-agent messages |
| Session | `SessionContract`, `ExecutionSessionContract` | Durable turns, checkpoint |
| Observability (×m) | `RecorderContract`, OTel plugins | Observe **everything** (§8) |

### 5.2 Orchestration

| Machine | Contract | Role |
|---------|----------|------|
| DP (one of ⊔) | `DesignPatternContract` | Schedule iterations; emit THINK/ACT/FINALIZE |
| Coordination (opt.) | `CoordinationContract` | Multi-agent topology |

### 5.3 Capabilities (effects)

| Machine | Contract | Role |
|---------|----------|------|
| Model | `ModelContract` | `complete()`, embeddings |
| Context | `ContextContract` + assembler + manager | Build `messages[]` + provenance (§7) |

### 5.4 Context sources (unified)

See §6 — memory, tools, skills are **not** separate semantic categories; they are **sources** with different `ContextProvenance.mechanism` and `source_type`.

### 5.5 Governance (×n)

| Plugin examples | When |
|-----------------|------|
| Budget | authorize: token/cost limits; validate: usage recorded |
| Sandbox | authorize: tool/path allow-list |
| Routing / policy | authorize: model/route constraints |

Each is \(M_{\text{gov}_i}\) in the family product. **All** must pass on symbols 2 and 6 for the call to proceed.

---

## 6. Context sources — one semantic kind, three calling paths

### 6.1 Unified thesis

> **Tool, memory, and skill are context sources.**  
> They answer queries and return **context** (`ContextPart` or message-shaped content).  
> The differences are **calling semantics** and **provenance**, not automaton kind.

| Source | Typical `source_type` | `mechanism` | Who initiates | When |
|--------|----------------------|-------------|---------------|------|
| Role / prompt template | `prompt` | `inject` | Runtime | Pre-LLM collect |
| DP instructions | `dp` | `inject` | Runtime | Pre-LLM collect |
| Skill catalog (facet) | `skill` | `inject` | Runtime | Pre-LLM collect |
| Tool directory (facet) | `tool` | `inject` | Runtime | Pre-LLM collect |
| Working memory (default feed) | `memory` | `inject` | Context manager | Pre-LLM assemble |
| Semantic / vector memory | `memory` | `rag` | Context manager | Pre-LLM collect |
| Full source catalog (platform-style) | `skill` / `agent` / `tool` | `inject` | Plugin config | Pre-LLM collect |
| `consult_skills` tool | `skill` | `tool_call` | LLM | Mid-loop |
| `memory_read` / WM tools | `memory` | `tool_call` | LLM | Mid-loop |
| Deterministic calculator, etc. | `tool` | `tool_call` | LLM | Mid-loop |
| RAG tool (retrieval tool) | `memory` / `rag` | `tool_call` | LLM | Mid-loop |

**Provenance is uniform:** every contribution is a `ContextPart` with `ContextProvenance` (`mechanism`, `actor`, `source_type`, `source_id`, `via`, `semantic_role`). Whether RAG ran inside the assembler before the call or a tool fetched chunks after the call, the **same** observability path records a context segment with the appropriate `mechanism`.

### 6.2 Source machines inside the product

Let context sources be **plugins** that implement `ContextContract.collect_context()` and optionally `ToolContract.call()` for the stochastic path.

Structurally:

\[
M_{\text{src}}^{\otimes k} = M_{\text{src}_1} \otimes \cdots \otimes M_{\text{src}_k}
\]

On `CTX_COLLECT_EXECUTE`, each source machine either:

- Emits `EMIT_PARTS` (list of `ContextPart`), or
- `NO_OUTPUT` if not contributing this turn.

**Stochastic path:** LLM emits tool call → \(\mathcal{E}_{\text{tool}}\) runs → result appended to `messages[]` → **second** context pass `CTX_COLLECT_POST_TOOL` (or reuse collect with `step` index > 0) merges tool-returned text into the same provenance model with `mechanism=tool_call`.

There is **no** semantic fork between "RAG before" and "tool after" — only **when** the collect phase runs and **who** triggered it.

### 6.3 Context memory — three layers (do not conflate)

“Working memory” appears in three **distinct** layers. Confusing them causes double
injection (same text in both `messages[]` and a `ContextPart`) or missing context
across turns.

| Layer | Store | What it holds | How it reaches the LLM |
|-------|-------|---------------|------------------------|
| **L1 — Transcript** | `SessionState.history`, live `messages[]` | User/assistant/tool turns from prior steps | **Not** via `collect_context`; loaded by session + **ContextManager** (`manage_history`) |
| **L2 — Structured stores** | WM KV (`working_memory_*` tools), `MemoryContract`, `MEMORY.md`, blackboard | Facts, embeddings, session-scoped KV, workspace files | **Re-read each step** via `collect_context` (`inject` / `rag`) or **stochastic** via `memory_read` tool |
| **L3 — Pattern state** | `DPState.memory` | Plan steps, executed results, failures, ToT tree | **Control only**; only fragments surface via DP `collect_context` (phase-dependent instructions) |

**Ephemeral vs durable (code mapping):**

- `AgentState` — per-run, one LLM step (`runtime/contracts/session_contract.py`).
- `SessionState` — durable per contact/channel; survives `handle_task` invocations.
- `ExecutionSession` — Mealy-layer checkpoint (`dp_state`, token usage, in-flight loop).
- `DPState.memory` — pattern-internal; orthogonal to Mealy lifecycle states.

#### Dedup rules (avoid repeating the same bytes)

| Content already in… | Do **not** also… |
|---------------------|------------------|
| `messages[]` (recent assistant / tool turns) | RAG-retrieve identical chunks into `SYSTEM_MEMORY` |
| WM KV injected last turn, value unchanged | Re-inject full snapshot (prefer delta, pin, or cache) |
| Static facets (`TOOLS.md`, role, DP protocol) | Worry about transcript duplication — re-collect is fine; `ContextFacetProvider` **caches** within a session |

Re-running `collect_context` every pre-LLM step does **not** mean copying everything
into a new WM blob. It means **re-projecting** stores onto the prompt:

- **Transcript** is already in `messages[]` — CM carries it forward.
- **Static sources** cache (facets, workspace files).
- **RAG** re-queries with `CollectContextRequest.query` (intentionally fresh per turn).
- **RetentionPolicy** / `WorkingMemoryAnnotation` verdicts (`retain`, `stale`,
  `low_score`, `dropped`) govern memory-store items at assembly time.

**Bounding** is policy, not architecture:

- `SummarisingConversation` (CM) compresses **history** (L1), not necessarily L2 stores.
- `MaxTokenStrategy` evicts **parts** by priority — expedient to keep context finite.
- The automaton requires **explicit provenance** when content is dropped (`_evicted_parts`
  → observability), not a specific summarisation strategy.

### 6.4 Tool dual-channel — prompt catalog vs execution API

Tools participate in **two orthogonal channels**. Same registry (`collect_tools`);
different surfaces:

| Channel | Payload | Placement / API | Purpose | Tracked as |
|---------|---------|-----------------|----------|------------|
| **Prompt catalog** | Names + descriptions (text) | `ContextPart` → `SYSTEM_TOOLS` band (priority 30–39) | Planning, DP protocols, prose tool choice | `context_part_contributed`; `mechanism=inject`, `source_type=tool` |
| **Execution catalog** | JSON schemas for function calling | `available_tools` param on `ModelContract.complete()` | Native `tool_calls` dispatch when DP allows | Gov envelope on `llm_execute`; not a context segment |

**Contributors for the prompt channel:**

- `ContextFacetProvider` / `TOOLS.md` workspace file → `SYSTEM_TOOLS`.
- Dedicated **tool-catalog context provider** (target): `collect_tools()` → render
  `ContextPart.tools(...)` — not yet a single default plugin; PlanExecute inlines
  names in DP instructions today.
- DP `_get_dp_instructions(available_tools)` — phase-specific protocol at `SYSTEM_PATTERN`.

**Execution channel controls (DP, not assembler):**

- ReAct: native tools **on** every THINK step (adapter or `next_action`).
- Plan-Execute: native tools **off** during PLAN, REPLAN, synthesis (`THINK_TEXT_ONLY`
  control signal); runtime executes plan steps via `DPAction(tool)` without model
  tool calls between steps.

Plan phase needs **descriptions in prompt**; execute phase needs **schemas for the
runtime**, not ad-hoc model tool calls during planning.

### 6.5 DP injection vs assembler tracking — division of labour

| Responsibility | Owner | Mechanism |
|----------------|-------|-----------|
| **What** to inject (CoT protocol, plan JSON format, RAG chunks, role text) | Contributors: DP, memory bridge, facets, workflow injector | `collect_context()` → `ContextPart` with `ContextProvenance` |
| **Assembly + provenance ledger** | `ContextAssemblerPlugin` (sub-phase of \(M_{\text{ctx}}\)) | `collect_results("collect_context")` → order → budget → write `messages[]` → `_context_segments` |
| **History compression** | `ContextManagerContract` (sub-phase of \(M_{\text{ctx}}\)) | `manage_history(past_turns)` — never mutates `ContextPart`s |
| **Execution surface control** | DP (`on_pre_llm_call` today → `DPMachine` output tomorrow) | Strip or pass `available_tools`; **not** context text |

DP implements `DesignPatternContract.collect_context()` — subclasses override
`_get_dp_instructions()`, not `collect_context()` directly:

```python
ContextPart(
    placement=SYSTEM_PATTERN,
    provenance={"mechanism": "design_pattern_injection", "source_type": "design_pattern", ...}
)
```

RAG / memory plugins use the **same pipe** with `mechanism=rag` or `inject`.
The assembler is the **single choke point** for “what entered the prompt this step.”

**Exception:** `available_tools` mutation is a **call-envelope control signal**
(`THINK_TEXT_ONLY`), audited via model pre-call governance/obs, not merged into
system-message segments.

---

## 7. Context assembler and context manager in the scheme

Historically the codebase splits two classes:

| Component | Contract / class | Responsibility |
|-----------|------------------|----------------|
| **Context manager** | `ContextManagerContract` | Transform **past conversation turns** (`manage_history`) |
| **Context assembler** | `ContextAssemblerPlugin` | Collect parts, order, budget, write `messages[]` |

In the **product model**, both are **sub-phases of a single** \(M_{\text{ctx}}\) — not peer product factors.

### 7.1 States of \(M_{\text{ctx}}\)

Logical state graph (implementation may interleave budget check and DP control signals):

```
IDLE
  → FILTER_HISTORY (ContextManager: manage_history on past turns)
  → COLLECTING     (run all ContextContract.collect_context on CTX_COLLECT_EXECUTE)
  → FILTER_PARTS   (ContextStrategy: token budget, eviction)
  → ASSEMBLING     (placement ordering, write messages[])
  → EMIT_PROVENANCE (side channel: _context_segments, context_part_contributed)
  → DONE → IDLE
```

`ContextAssemblerPlugin` runs history filter **before** collect (see §26.3). DP
`THINK_TEXT_ONLY` control applies to the model envelope **after** assembly, on the
hook bus or via `DPMachine` output.

### 7.2 Envelope for context assembly

\[
\mathcal{E}_{\text{ctx}} =
\texttt{ctx\_collect\_start}
\circ \texttt{ctx\_collect\_execute}
\circ \texttt{ctx\_collect\_end}
\circ \texttt{ctx\_filter\_start}
\circ \texttt{ctx\_filter\_execute}
\circ \texttt{ctx\_filter\_end}
\circ \texttt{ctx\_assemble\_start}
\circ \texttt{ctx\_assemble\_execute}
\circ \texttt{ctx\_assemble\_end}
\]

Each `_start` / `_end` pair is wrapped by Obs\* (and Gov\* if policy applies to context content, e.g. PII rules on injected memory).

**Filter phase decomposition:**

| Sub-step | Implementation | Input | Output |
|----------|----------------|-------|--------|
| History filter | `CMFactory` → `manage_history` | Past user/assistant turns | Trimmed history |
| Parts filter | `ContextStrategy` / `MaxTokenStrategy` | `ContextPart[]` | Trimmed parts + evicted list |
| Assembly | Placement bands + priorities | Trimmed parts + history + live user turn | `messages[]` |

### 7.3 Why merge assembler + manager

- **Single provenance emitter:** one machine owns `_context_segments`, `_evicted_parts`, `_summarized_turns`.
- **Single ordering policy:** history compression and part injection interact (summary blocks are themselves `ContextPart`s).
- **One collect semantics** for pre-LLM and post-tool: the same \(M_{\text{ctx}}\) graph runs again with updated `TransitionContext.messages` and `step` index.

Legacy names remain in code (`ContextAssemblerPlugin`, `CMFactory`); architecturally they are **transitions inside** \(M_{\text{ctx}}\).

---

## 8. Observability and governance interaction

### 8.1 Observability monitors governance

On symbol `governance_authorize` (step 2 of envelope):

- Each \(M_{\text{gov}_i}\) steps → allow/deny decision.
- Each \(M_{\text{obs}_j}\) steps → `EMIT_EVENT` recording **each** governance decision (machine id, policy id, allow/deny, rationale code).

On symbol `governance_validate` (step 6):

- Same pattern for post-execution validation.

Thus observability **does not only** monitor LLM/tool calls; it monitors **governance before and after** those calls (and before/after context assembly if gov is configured for `ctx`).

### 8.2 Invariants

| Invariant | Statement |
|-----------|-----------|
| Obs coverage | ∀σ ∈ envelope, ∀j: \(M_{\text{obs}_j}\) fires on σ |
| Gov coverage | ∀ critical calls, ∀i: \(M_{\text{gov}_i}\) fires on `governance_authorize` and `governance_validate` |
| Gov denial | ∃i deny on symbol 2 or 6 ⇒ call aborted, no `execute_fn` (symbol 2) or result rejected (symbol 6) |
| Obs equivalence | No observer is downstream of another; order is registration order only |
| Fail-open obs | Obs machine error → isolated to ERROR state; must not block gov or capability |

### 8.3 Span structure (conceptual)

```
span: agent.turn
  span: context.collect
    event: context.part {provenance...} × N
    event: context.evicted × M
  span: model.generate
    event: governance.authorize
    event: governance.validate
    event: model.tokens
  span: tool.execute (×k)
    event: governance.authorize
    event: governance.validate
    event: context.part {mechanism: tool_call}
```

---

## 9. Design patterns as schedulers (ReAct is one)

\(M_{\text{DP}}^{(p)}\) states map to **phases** (`DPPhase`: DECIDE, PLAN, ACT, OBSERVE, FINALIZE, WAIT_EVENT, …). These are **orthogonal** to runtime lifecycle states (`IDLE`, `REASONING`, `ACTING`).

### 9.1 Generic iteration (pattern-neutral)

```
iteration_start
  DP → emit COLLECT_CONTEXT
  E_ctx
  loop:
    DP → emit THINK | ACT | FINALIZE | WAIT
    if THINK:
      E_llm(model)
      DP consumes LLM_RESPONSE
    if ACT:
      E_tool(source)      // any context source on stochastic path
      E_ctx'              // merge tool result; same provenance model
      DP consumes TOOL_RESULT
    if FINALIZE:
      break
  session.save_turn
iteration_end
```

### 9.2 ReAct as instantiation

| ReAct step | DP phase | Product envelopes |
|------------|----------|-------------------|
| Reason | DECIDE → THINK | \(\mathcal{E}_{\text{ctx}}, \mathcal{E}_{\text{llm}}\) |
| Tool use | ACT | \(\mathcal{E}_{\text{tool}}, \mathcal{E}_{\text{ctx}'}\) |
| Observe | OBSERVE | (context merge only) |
| Answer | FINALIZE | session persist |

### 9.3 CoT / Plan-Execute / others

- **CoT:** DP skips ACT branch until FINALIZE; extra THINK iterations via `should_continue`.
- **Plan-Execute:** see §28 for full phase diagram; PLAN uses text-only LLM + tool names in
  prompt; ACT is runtime-driven from parsed JSON plan.
- **EventLoopDP:** FINALIZE → `WAIT_EVENT` instead of agent end; session machine stays ACTIVE.

The product formula **does not change** — only \(M_{\text{DP}}^{(p)}\) and the scheduler edges change.

### 9.4 ReAct vs Plan-Execute — scheduling contrast

| Aspect | ReAct | Plan-Execute |
|--------|-------|----------------|
| Who picks the next tool? | Model every THINK step | Model only in PLAN/REPLAN (JSON); **runtime** in ACT |
| Native function calling | On every THINK (§20 adapter allowed) | **Off** during PLAN, REPLAN, synthesis |
| Tool awareness when planning | Native API + optional `SYSTEM_TOOLS` text | Tool **names** in prompt (`_get_dp_instructions` or catalog facet) |
| Loop shape | DECIDE → ACT → OBSERVE → DECIDE … | PLAN → ACT (sequential tools, no LLM between steps) → synthesis THINK → FINALIZE |
| Tool error recovery | Stay in DECIDE; inject feedback | REPLAN (not DECIDE — PlanExecute does not handle DECIDE) |

**OSS implementation reference:** `runtime/src/mas/runtime/machines/design_pattern/plugins/react.py`,
`runtime/src/mas/runtime/machines/design_pattern/plugins/plan_execute.py`; integration tests in
`runtime/tests/integration/test_design_pattern_plugins_integration.py`.

---

## 10. Global input alphabet (reference)

Lifecycle:

- `agent_start`, `agent_end`, `iteration_start`, `iteration_end`, `shutdown`, `interrupt_signal`, `contract_error`

Context:

- `ctx_collect_start`, `ctx_collect_execute`, `ctx_collect_end`
- `ctx_filter_start`, `ctx_filter_execute`, `ctx_filter_end`
- `ctx_assemble_start`, `ctx_assemble_execute`, `ctx_assemble_end`
- `ctx_post_tool_collect_*` (optional explicit; or reuse collect with metadata)

Per capability \(c \in \{\text{model}, \text{tool}, \text{memory}, \text{transport}, \ldots\}\):

- `{c}_{op}_start`, `{c}_{op}_execute`, `{c}_{op}_end`
- `governance_authorize`, `governance_validate`
- `observability_pre_execute`, `observability_post_execute`

DP-specific (internal to DP machine, may map to global symbols):

- `user_message`, `llm_response`, `tool_result`, `plan_ready`, `sensor_event`

---

## 11. TransitionContext — shared tape

The product shares a **context tape** (not part of Mealy state):

```python
TransitionContext:
  messages: List[Message]       # current LLM-facing list
  parts: List[ContextPart]    # collected this turn
  provenance_log: List[...]   # append-only for obs
  session_id, step, task_id
  metadata: { result, tool_name, query, ... }
```

Machines read/write the tape through guarded transitions. **Determinism** is w.r.t. machine outputs given (state, σ, tape); `execute_fn` impurity is outside.

---

## 12. From formula to manifest

```yaml
# Conceptual agent manifest (illustrative)
orchestration:
  dp:
    type: react          # selects M_DP^{(react)} from sum

capabilities:
  context:
    conversation_manager: sliding-window   # CM summand
    context_strategy: max-tokens
    sources:
      - type: working_memory
        default_inject: true
      - type: semantic_memory
        mechanism: rag
      - type: skill_catalog
        mechanism: inject
      - type: tools
        mechanism: inject
        tools: [consult_skills, calculator, memory_read]

  model:
    provider: openai

governance:
  - type: budget
  - type: sandbox

observability:
  - type: otel
  - type: native   # second observer, equivalent coverage
```

`manifest_to_machines(config)` → register each plugin as one or more Mealy machines → `create_agent_product(machines)`.

---

## 13. Kernel pseudocode (target runtime)

```python
class AgentKernel:
    def __init__(self, product: MealyProductIntegration, dp: DPMachine):
        self.product = product
        self.dp = dp

    def handle_task(self, task):
        ctx = TransitionContext.from_task(task)
        self.product.step(Input.AGENT_START, ctx)

        while True:
            self.product.step(Input.ITERATION_START, ctx)
            out = self.dp.output  # read DP machine output from last step

            # Context (always same machine, same provenance model)
            self._run_envelope("ctx", "collect", lambda: self._collect_sources(ctx))
            self._run_envelope("ctx", "filter", lambda: self._filter_context(ctx))
            self._run_envelope("ctx", "assemble", lambda: self._assemble_messages(ctx))

            action = self._resolve_dp(out)
            if action == "FINALIZE":
                break
            if action == "THINK":
                self.product.execute_contract_call(
                    "model", "generate",
                    lambda: self.model.complete(ctx.messages),
                    ctx,
                )
            if action == "ACT":
                self.product.execute_contract_call(
                    "tool", "execute",
                    lambda: self._execute_tool(ctx),
                    ctx,
                )
                # Post-tool context merge — same M_ctx, mechanism=tool_call
                self._run_envelope("ctx", "collect", lambda: self._collect_post_tool(ctx))

            self.product.step(Input.ITERATION_END, ctx)

        self.product.step(Input.AGENT_END, ctx)
        return ctx.final_response
```

**No ReAct-specific branch** — only DP outputs and envelopes.

---

## 14. Implementation map (v0.1 OSS — current vs target)

**Last reconciled:** 2026-06. For CI-enforced status see [mealy-envelope.md](mealy-envelope.md) §2.

| Concept | Target | v0.1 codebase |
|---------|--------|---------------|
| Product ⊗ | General `GuardedProductComposer` over n summands | **Shipped:** `M_obs ⊗ M_gov ⊗ M_capability` via `get_product_composer()` |
| Gov family ⊗ⁿ | Separate Mealy per policy dimension | **Partial:** policy engine + egress chokepoint; single `GovEnvelopeMachine` |
| Obs family ⊗ᵐ | Separate Mealy per obs channel | **Partial:** `ObsEnvelopeMachine` + `ObservabilityOperator` |
| \(M_{\text{ctx}}\) unified | Single context machine | **Shipped:** context assembly before LLM egress; CM plugins |
| Sources unified | `collect_context` + tool path | **Shipped:** same `ContextPart` model |
| DP scheduler | `evaluate_next` / `handle_event` drives egress | **Shipped:** `RuntimeKernel` + DP plugins (`react`, `plan_execute`, …) |
| Plan-Execute | Text-only plan + runtime tool execution | **Shipped:** `PlanExecutePlugin` in registry; kernel integration tests |
| Context assembler | Collect → filter → assemble → provenance | **Shipped:** hot path before each `LLM_CALL` |
| Tool catalog facet | `collect_tools` → prompt facet | **Partial:** manifest tools; auto-bridge varies by flavour |
| 7-symbol envelope | `execute_contract_call` / chokepoints | **Shipped:** TOOL and LLM hot paths via `egress_gate.py` |
| Provenance | `ContextProvenance` → obs | **Shipped:** `context_assembled` events |
| Session persistence | Policy-selected turn log | **Partial:** final turn in session; full trace in `events.jsonl` |
| Post-tool ctx pass | Post-tool `collect_context` | **Partial:** kernel supports; not all labs enable |
| Offline `ProductMealyComposer` | ⊗ materialization for model checking | **Not shipped** (design-only reference in §3) |

---

## 15. Summary

| Question | Answer |
|----------|--------|
| Is the agent a plain product? | **Mostly ⊗** over orthogonal dimensions, plus **⊔** for DP/CM variant, plus **∘** for call envelopes, plus **μ** for DP iteration |
| Where do tool/memory/skill live? | Inside **context sources**; same `ContextPart` + provenance; differ by `mechanism` and initiator |
| Assembler vs manager? | **Sub-phases of** \(M_{\text{ctx}}\): collect → filter history → filter parts → assemble → emit provenance (§7, §26.3) |
| Context vs working memory? | Three layers L1 transcript / L2 stores / L3 DP state — §6.3, §26 |
| Tool prompt vs tool API? | Dual-channel — §6.4, §27 |
| DP injection tracking? | DP chooses *what* via `collect_context`; assembler tracks via `_context_segments` — §6.5 |
| Governance? | **⊗ⁿ** family; authorize + validate on every critical call |
| Observability? | **⊗ᵐ** family; observes **all** symbols including governance |
| ReAct? | **One** \(M_{\text{DP}}^{(\text{react})}\) scheduler; not the architectural center |
| Plan-Execute? | Text-only plan + runtime tool execution — §9.4, §28 |

The automaton is **richer than a single product**:

\[
M_{\text{agent}} =
\mu \text{turn}.\;
\mathcal{E}_{\text{ctx}}
\circ \text{sched}\bigl(M_{\text{DP}}^{(p)}\bigr)
\circ \bigl(\otimes_i M_i\bigr)
\]

where \(\text{sched}(M_{\text{DP}})\) emits sequences of \(\mathcal{E}_{\text{call}}\) envelopes, and \(\otimes_i M_i\) is the synchronous parallel product of session, model, sources, governance family, and observability family — stepped on every symbol in those envelopes.

That is the full model the runtime should converge to.

---

## 16. Complete contract registry → framework mapping

Every contract exported from `mas.runtime.contracts` (and adjacent factories) must
fit the product model without special cases. The table below is the authoritative
placement guide.

### 16.1 Capability contracts

| Contract ID | Class | Machine / envelope | Role in product |
|-------------|-------|-------------------|-----------------|
| `context` | `ContextContract` | \(M_{\text{ctx}}\) collect phase + source ⊗ | Contributors emit `ContextPart`; facets, memory bridge, DP instructions |
| `context_manager` | `ContextManagerContract` | \(M_{\text{ctx}}\) filter-history sub-phase | `manage_history()` — not a separate product factor |
| `tool` | `ToolContract` | Source (stochastic) + \(\mathcal{E}_{\text{tool}}\) | `call_tool` when DP emits `ACT`; directory facet when `inject` |
| `memory` | `MemoryContract` | Source (rag/inject) + \(\mathcal{E}_{\text{memory}}\) | `read`/`write`/`query`; WM tools are tool-shaped sources |
| `model` / `llm` | `ModelContract` | \(M_{\text{model}}\) + \(\mathcal{E}_{\text{llm}}\) | `complete()` / embeddings |
| `prompt` | `PromptContract` | \(\mathcal{E}_{\text{prompt}}\) or ctx collect | Template fetch; maps to `pre_prompt_build` hooks today |
| `session` | `SessionContract` | \(M_{\text{session}}\) | Turn log, `windowed_history`, contact metadata |
| `execution` | `ExecutionSessionContract` | \(M_{\text{session}}\) checkpoint sub-state | Mealy-layer `ExecutionSession` persistence |
| `recorder` | `RecorderContract` | One summand of \(M_{\text{obs}}^{\otimes m}\) | Low-level event sink inside observability family |
| `sensor` | `SensorContract` | Transport/session ingress | `SensorEvent` → `USER_MESSAGE` / `sensor_event` symbols |
| `control` | `ControlContract` | DP + session guards | `steer()` → `INTERRUPT_SIGNAL`; queued for next iteration |
| `message` | `MessageContract` | \(\mathcal{E}_{\text{transport}}\) | Simple send; subset of transport |
| `transport` | `TransportContract` | \(M_{\text{transport}}\) | Bus unicast/broadcast, delivery ack |
| `delegation` | `DelegationContract` | Tool + coordination | `DelegateTaskTool` — tool envelope + coord dispatch |
| `shared_context` | `SharedContextContract` | Context source (`inject`) | Blackboard → `ContextPart`, `source_type=shared` |
| `gateway` | `GatewayContract` | Transport + session + surface | Persistent agent lifecycle, channel routing |
| `surface` | `SurfaceAdapter` | Outside product (I/O boundary) | CLI/WebSocket envelopes → `USER_MESSAGE` / `user_output` |
| `dp` | `DesignPatternContract` | \(M_{\text{DP}}^{(p)}\) ⊔ summand | Turn scheduler only |
| `chat` | `ChatContract` | Surface + session (lazy) | OC-parity; optional summand |

**Context:** `ContextContract` — context assembly from all sources (memory, tools, sub-agents, skills, …).

**Moved out of agent product:** `EvalContract` → `mas.lab.evaluation` (benchmark
pipeline only; not stepped during `handle_task`).

### 16.2 Orchestration contracts

| Contract ID | Class | Machine | Role |
|-------------|-------|---------|------|
| `workflow` | `WorkflowContract` (= `CoordinationContract`) | \(M_{\text{coord}}\) ⊔ variant | Topology driver: dynamic, supervised, sequential, graph |
| `coordination` | `CoordinationContract` | \(M_{\text{coord}}\) | Multi-agent routing, fan-out, barrier, vote |

Workflow plugins (`DynamicWorkflow`, `GraphWorkflow`, …) select **one** coordination
summand at MAS scope. Single-agent runs omit \(M_{\text{coord}}\).

### 16.3 Governance contracts

| Contract ID | Class | Machine | Authorize / validate on |
|-------------|-------|---------|-------------------------|
| `budget` | `BudgetContract` | `governance_budget` | LLM, tool, memory (token/cost ceilings) |
| `routing` | `RoutingContract` | `governance_routing` | Topology edges (future) |
| `sandbox`, `tbac` | *(mas-lab-internal only)* | — | Proprietary extensions; not shipped in OSS |

Library-standard also ships **governance plugins** (not separate contract types)
that map to governance machines:

| Plugin | Maps to |
|--------|---------|
| `BudgetPlugin` | `governance_budget` |
| `GuardrailPlugin` | `governance_guardrail` |
| `CircuitBreakerPlugin` | `governance_circuit_breaker` |
| `HITLPlugin` | `governance_hitl` (may gate tool machine `WAITING_HITL`) |
| `GuardBundle` | meta-registration of several gov machines |

All governance instances are **⊗** — every call runs authorize + validate on **all**
registered gov machines.

### 16.4 Observability plugins → obs family

Each observability plugin is one \(M_{\text{obs}_j}\). All implement
`ObservabilityPluginBase` / `OBSERVABILITY_HOOKS` — mapped to product symbols:

| Hook (today) | Product symbol(s) | Obs output |
|--------------|-------------------|------------|
| `on_pre_execution` | `agent_start`, `iteration_start` | `EMIT_SPAN` |
| `on_post_execution` | `iteration_end`, `agent_end` | `CLOSE_SPAN` |
| `on_post_context_assembly` | `ctx_assemble_end` | `EMIT_EVENT` + provenance segments |
| `on_post_llm_call` | `llm_execute`, `obs_post_execute` | `EMIT_EVENT` |
| `on_pre_tool_call` / `on_post_tool_call` | `tool_*` envelope | `EMIT_EVENT` |
| `on_pre_memory_read` / `on_post_memory_read` | `memory_read_*` | `EMIT_EVENT` |
| `on_pre_memory_store` / `on_post_memory_store` | `memory_write_*` | `EMIT_EVENT` |
| `on_governance_event` | `governance_authorize`, `governance_validate` | `EMIT_EVENT` |
| `on_pre_skill_execution` / `on_post_skill_execution` | `tool_execute` (skill tools) | `EMIT_EVENT` |
| `on_pre_agent_communication` / `on_post_*` | `transport_*` | `EMIT_EVENT` |
| `on_user_input` / `on_user_output` | surface → `USER_MESSAGE` / finalize | `EMIT_EVENT` |

**Parity rule:** adding a new obs plugin = registering another \(M_{\text{obs}_j}\);
no kernel change. Each sees the full symbol stream including governance decisions.

### 16.5 Library-standard plugins as context sources

Plugins that are not standalone contracts still fit as **context sources** or
**envelope backends**:

| Plugin category | Framework placement |
|-----------------|---------------------|
| `RoleInstructionsProvider`, `FilePromptProvider`, `FewShotPlugin` | ctx collect, `inject`, `source_type=prompt` |
| `ContextFacetProvider`, `WorkflowPromptInjector` | ctx collect, `inject`, skills/agents/tools directories |
| `SkillPlugin`, `SkillEligibilityChecker` | ctx collect + `consult_skills` tool path |
| `MemoryContextPlugin`, vector/Letta overlays | ctx collect, `rag` or `inject` |
| `DefaultContextPlugin`, `ContextPolicyPlugin` | ctx filter / governance overlay on parts |
| `OpenAIModelAccess`, `MockModelAccess` | `execute_fn` behind \(\mathcal{E}_{\text{llm}}\) |
| `ToolProviderPlugin`, `LocalToolProvider`, `system_tools` | tool envelope + tool directory facet; target `ToolCatalogContextProvider` (§27.3) |
| `PlanExecuteDP`, `ReactDP`, other DPs | ctx collect `SYSTEM_PATTERN` + DP scheduler (§28) |
| `LocalTransportPlugin`, `GRPCTransportPlugin` | \(M_{\text{transport}}\) |
| `DynamicWorkflow`, `GraphWorkflow`, … | \(M_{\text{coord}}\) ⊔ |
| `CLISurfaceAdapter`, `WebSocketSurfaceAdapter` | Surface boundary → kernel events |

---

## 17. DPPhaseMachine vs DPMachine — two layers, one scheduler

The codebase has **two** DP-related automata; the document uses one abstract
\(M_{\text{DP}}^{(p)}\) but implementers need both:

| Construct | Layer | Purpose |
|-----------|-------|---------|
| `DPPhaseMachine` | L1 formal graph | Declarative phase FSM (`DPPhase` edges); liveness at `DPFactory.register`; `to_mealy_machine()` for model checking |
| `DesignPatternContract` | L3 plugin API | `start`, `next_action`, `on_action_result`, `should_continue`, `finalize`, `collect_context` |
| `DPMachine` (stub) | L1 product slot | Product-integrated scheduler emitting `THINK`/`ACT`/`FINALIZE` |

**Relationship:**

\[
M_{\text{DP}}^{(p)} = \text{realize}\bigl(\text{DPPhaseMachine}_p,\; \text{DPContract impl}_p\bigr)
\]

- `DPPhaseMachine` is the **spec** (reachable phases, legal edges).
- `next_action()` is the **implementation** (must respect the spec; `ValidatedDP` enforces at runtime).
- `DPMachine` in the product is the **adapter** that reads plugin outputs and emits kernel commands.

**Builtin phase machines** (`dp_phase_machine.py`): `react_phase_machine`,
`event_loop_phase_machine`, `accumulator_phase_machine`, plus per-DP
`get_phase_machine()` on each plugin class.

---

## 18. All OSS design patterns — scheduler profiles

Changing `spec.design_pattern.type` selects a different ⊔ summand. The **product
formula is unchanged**; only phase graph and emitted actions differ.

| Pattern | Registry name | Phase highlights | `THINK` | `ACT` | Notes |
|---------|---------------|------------------|---------|-------|-------|
| **ReAct** | `react` | DECIDE ↔ ACT ↔ OBSERVE | LLM reasoning | Tools / skills / memory tools | Native `tool_calls` adapter allowed (§20) |
| **CoT** | `cot` | DECIDE loop → FINALIZE | Chain-of-thought LLM steps | Rare / none | Lab: `pattern-cot.yaml` |
| **Plan-Execute** | `plan_execute` | PLAN → ACT → (REPLAN) → synthesis → FINALIZE | Plan / replan / synthesis LLM (text-only) | Runtime executes plan via `DPAction(tool)` — no model tool calls between steps | §28; `test_design_patterns.py` |
| **Tree of Thoughts** | `tree_of_thoughts` | EXPAND, EVALUATE, BACKTRACK | Multiple LLM samples | Optional tool | Lab: `pattern-tree-of-thoughts.yaml` |
| **Introspection** | `introspection` | REFLECT / CRITIQUE phases | Self-critique LLM | Optional | Lab: `pattern-reflection.yaml` |

**Event-driven / accumulator patterns** (sensor-fed, not in all labs): use
`WAIT_EVENT`, `COLLECT`, `READY` phases — `event_loop_phase_machine`,
`accumulator_phase_machine`.

### 18.1 DP swap checklist (manifest-only, once kernel is migrated)

1. Set `spec.design_pattern.type` to registry name (`react`, `cot`, …).
2. Ensure pattern-specific overlays only change DP + prompt parts (not kernel).
3. Verify `DPFactory` liveness log on startup (FINALIZE reachable).
4. Run `library-standard/tests/test_design_patterns.py` for the pattern.
5. Run affected lab experiment with same `--flavour` / `--infra` as before.
6. Compare OTel/events JSONL: same span kinds, possibly different step counts.

**No change required** to context sources, governance ⊗ⁿ, observability ⊗ᵐ, or
session when swapping DP.

---

## 19. Multi-agent and I/O boundaries

### 19.1 Coordination ⊗ (optional)

When `spec.agency` / workflow topology is not single-agent:

\[
M_{\text{agent}} \otimes M_{\text{coord}}^{(w)}
\]

where \(w \in \{\text{dynamic}, \text{supervised}, \text{sequential}, \text{graph}, \text{async\_dynamic}\}\).

Coordination emits: `ROUTE`, `DISPATCH`, `BARRIER`, `COLLECT_VOTE`, `EMIT_RESULT`.
Each dispatch wraps delegate calls in \(\mathcal{E}_{\text{tool}}\) or
\(\mathcal{E}_{\text{transport}}\) with the same gov/obs envelopes.

**Labs using topologies:** `design-space.lab/02-topologies` (supervised, linear-pipeline,
parallel, moderator-broker, verifier).

### 19.2 Transport, gateway, delegation

| Mechanism | Contracts | Envelope |
|-----------|-----------|----------|
| In-process delegate | `DelegationContract` | `tool.execute` + sub-agent `handle_task` |
| Bus / gRPC | `TransportContract` | `transport_send`, `transport_receive` |
| Persistent channels | `GatewayContract` | gateway lifecycle + transport |
| `SendToCallerTool` | Tool + surface | Returns via parent session |

### 19.3 Surface adapters (outside product)

Surfaces are **adapters**, not Mealy factors:

```
SurfaceAdapter.recv()  →  product.step(USER_MESSAGE)
product.step(user_output)  →  SurfaceAdapter.send()
```

CLI (`mas-runtime run-agent`), WebSocket, benchmark HITL — same kernel.

### 19.4 Sensor + control (reactive agents)

```
SensorContract.pull()  →  USER_MESSAGE or sensor_event
ControlContract.steer()  →  INTERRUPT_SIGNAL  →  DP phase INTERRUPT → DECIDE
```

---

## 20. ReAct adapter — native `tool_calls` without hard-coding the kernel

ReAct can be realized two ways; both are **the same** \(M_{\text{DP}}^{(\text{react})}\):

| Path | When |
|------|------|
| **Formal** | `ReactDP.next_action()` emits `ACT` with tool name + args |
| **Adapter** | After \(\mathcal{E}_{\text{llm}}\), map `response.tool_calls` → `ACT` + populate `TransitionContext` |

The adapter lives **inside** the ReAct summand or a thin `DPOutputResolver` — not in
the kernel loop. CoT/ToT/Plan-Execute **never** use the adapter; they require formal
`next_action()`.

This preserves backward compatibility with OpenAI-style function calling while keeping
the kernel pattern-neutral (§13).

---

## 21. Hook plane → product symbols (full equivalence)

Migration removes `HookPlane` phase numbers. Every hook maps to a product symbol;
governance and observability are **systematic**, not ad hoc plugin callbacks.

| Hook | Symbol sequence |
|------|-----------------|
| `pre_execution` | `agent_start` |
| `post_execution` | `agent_end` |
| `pre_context_assembly` | `ctx_collect_start` |
| `collect_context` | `ctx_collect_execute` |
| `post_context_assembly` | `ctx_assemble_end` (+ obs provenance) |
| `pre_prompt_build` | `prompt_fetch_start` … `prompt_fetch_end` |
| `pre_llm_call` (assembler) | `ctx_filter_*` + `ctx_assemble_*` + provenance emit |
| `pre_llm_call` (model gate) | `governance_authorize` + `observability_pre_execute` |
| `on_pre_llm_call` (DP control) | DP `THINK_TEXT_ONLY` / `THINK_WITH_TOOLS` on model envelope (§30.4) |
| `post_llm_call` | `llm_execute` + `observability_post_execute` + `governance_validate` |
| `pre_tool_call` | `governance_authorize` (tool) + `observability_pre_execute` |
| `post_tool_call` | `tool_execute` + `observability_post_execute` + `governance_validate` |
| `pre_memory_read` / `post_memory_read` | `memory_read_*` envelope (7 symbols) |
| `pre_memory_store` / `post_memory_store` | `memory_write_*` envelope |
| `governance_event` | folded into `governance_authorize` / `governance_validate` |
| `user_input` / `user_output` | `USER_MESSAGE` / finalize emit |

**Equivalence claim:** For any hook sequence \(H\) used by agents/labs today, there
exists a symbol sequence \(\Sigma^*\) such that stepping the product on \(\Sigma^*\)
with the same plugins registered produces the same **observable behaviour** (messages
to LLM, tool results, session persistence, events JSONL, OTel spans, governance
denials).

---

## 22. Seven-symbol envelope (inline reference)

Every side effect uses `MealyProductIntegration.execute_contract_call()`:

```
1. {contract}_{op}_start
2. governance_authorize     → ALL govᵢ; ALL obsⱼ record
3. observability_pre_execute → ALL obsⱼ
   [execute_fn() — kernel only]
4. {contract}_{op}_execute
5. observability_post_execute
6. governance_validate      → ALL govᵢ; ALL obsⱼ record
7. {contract}_{op}_end
```

Contracts using this envelope today in code: **any** `contract_type` string passed to
`execute_contract_call`. Target: **all** capability invocations (model, tool, memory,
prompt, transport, session checkpoint, ctx filter).

---

## 23. Lab and agent equivalence matrix

The migrated kernel must run **without manifest or overlay changes** (except optional
DP type swaps). Coverage by lab family:

| Lab / area | Stresses | Contracts / machines exercised |
|------------|----------|-------------------------------|
| `design-space.lab/01-design-patterns` | All OSS DPs | \(M_{\text{DP}}^{(p)}\), ctx, model, tool |
| `design-space.lab/02-topologies` | Multi-agent | \(M_{\text{coord}}\), delegation, transport |
| `extensions.lab` | Memory overlays (vector, Letta, tool-memory) | ctx sources rag/inject, memory envelope |
| `lifecycle-control.lab` | Budget, guardrail, circuit breaker, governance-off | gov⊗ⁿ, obs⊗ᵐ |
| `mas-runtime run-agent` | CLI single-shot / interactive | surface, session, ctx, model, dp |
| `ctl` trip-planner / statemachine | Workflow agents | coord, session, tool |
| Benchmark pipelines | OTel export, neo4j, service_start | obs, **outside** agent product (lab infra) |

**Out of agent product (unchanged):** `mas-lab benchmark` pipeline steps
(`export_otel`, `neo4j_push`, `service_start`), `EvalContract` metrics — these
consume artifacts **produced** by the agent product's observability family.

### 23.1 Equivalence validation plan

1. **Golden traces:** Record events JSONL + OTel per lab scenario on current runtime.
2. **Replay:** Same manifests on migrated kernel; diff span kinds + attributes (not raw timestamps).
3. **Contract tests:** `test_design_patterns.py`, `test_machine_composition.py`, `test_observability_plugin.py`.
4. **Lab smoke:** `--single-run` on each lab `experiment.yaml` in CI.
5. **Governance:** Deny paths (budget exhausted, sandbox violation) must raise same exceptions.
6. **DP bisimulation:** `DPPhaseMachine` / `check_bisimulation` for pattern refactors.

---

## 24. Shipped kernel shape (v2 OSS)

**Shipped (v0.1 OSS):** compact Mealy kernel under `mas/runtime/kernel/`, envelope hot path,
`RuntimeInstance` driver, ctl-owned bootstrap (`instantiate_runtime` / `SessionController`).

```
mas/runtime/
  kernel/                # RuntimeKernel — sole orchestration (§13)
  machines/              # DP / gov / obs Mealy machines
  driver/                # RuntimeInstance, run_turn, checkpoints
  factory/builder.py     # RuntimeBuilder embed entry
  contracts/             # plugin contracts + factories
  boundary/              # context assembly, skills injection
```

| Retired concept | Shipped replacement |
|-----------------|---------------------|
| Monolithic `runtime.py` loop | `RuntimeKernel` + product composition |
| Hook-plane phase numbers | Product symbols + envelope σ schedule (§21–§22) |
| `AgentBuilder` / `AgentRuntime` | `RuntimeBuilder` + `mas.ctl.SessionController` |
| Ad-hoc governance in LLM path | Gov machines on σ₂ / σ₆ |

**What stays:** Plugin classes, manifests, `DPFactory`, `CMFactory`, lab pipeline YAML,
overlay merge (`mas/v1` `Overlay` + `spec.patch`).

### 24.1 Systematic governance and observability (shipped)

```
∀ side effect e: wrap(e) = σ₁ ∘ … ∘ σ₇  (§22)
∀ govᵢ ∈ Gov: fire on σ₂, σ₆
∀ obsⱼ ∈ Obs: fire on σ₁…σ₇ including σ₂, σ₆
```

No capability call bypasses the envelope. Plugins never self-invoke governance;
the product always does. Observability never blocks (fail-open ERROR state per machine).

### 24.2 Verification gates (CI)

| Gate | Purpose |
|------|---------|
| `runtime/tests/test_mealy_envelope.py` | Envelope σ ordering |
| `runtime/tests/test_overlay_merge.py` | Canonical `mas/v1` overlays |
| `tests/test_golden_labs_run.py` | End-to-end lab parity |
| `ctl/tests/` | Compose, deployment, session |

---

## 26. Context memory layers — consolidated reference

This section restates §6.3–§6.5 as an operational guide for implementers.

### 26.1 Store once, project many, track always

> **Store** content in the right durable or ephemeral store.  
> **Project** a fresh LLM-facing view each step via \(M_{\text{ctx}}\).  
> **Track** every projected byte with provenance; log every eviction and control signal.

```
┌─────────────────────────────────────────────────────────────────┐
│ STORES (write targets)                                          │
│  SessionState.history │ MemoryContract │ WM KV │ DPState.memory │
│  MEMORY.md / workspace │ SharedContext blackboard               │
└────────────────────────────┬────────────────────────────────────┘
                             │ read / window / RAG
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ M_ctx per LLM step                                              │
│  1. CM.manage_history (L1 transcript)                           │
│  2. collect_context (DP, RAG, facets, tool catalog, …)         │
│  3. filter parts (token budget)                                 │
│  4. assemble messages[] + emit _context_segments                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ LLM payload: messages[] + available_tools (execution channel)   │
│ DP control: THINK_TEXT_ONLY | THINK_WITH_TOOLS                  │
└─────────────────────────────────────────────────────────────────┘
```

### 26.2 What is re-injected every call vs carried in transcript

| Material | Every `collect_context`? | Carried in `messages[]`? |
|----------|--------------------------|--------------------------|
| DP phase instructions | Yes (phase-dependent) | No — system band |
| Tool catalog descriptions | Yes (cached if static facet) | No — `SYSTEM_TOOLS` |
| RAG memory hits | Yes (query-dependent) | No — `SYSTEM_MEMORY` |
| Prior user/assistant turns | No | Yes — via session + CM |
| Tool results this turn | Appended after each tool | Yes — `role=tool` messages |
| Parsed plan / executed steps | No (L3 `DPState.memory`) | Only if synthesis prompts reference them |

### 26.3 Context manager vs assembler (joint orchestration)

Both are sub-phases of \(M_{\text{ctx}}\) — not competing injectors:

| Phase | Class | Input | Output |
|-------|-------|-------|--------|
| History filter | `ContextManagerContract` | Past user/assistant turns (excl. live user turn) | Trimmed / summarised history |
| Collect | All `ContextContract` plugins | `CollectContextRequest` (query, session_id, step, `available_tools` metadata) | `ContextPart[]` |
| Parts filter | `ContextStrategy` | All parts | Trimmed parts + `_evicted_parts` |
| Assemble | `ContextAssemblerPlugin` | Parts + history + live user turn | `messages[]`, `_context_segments`, `context_part_contributed` events |

**Assembler implementation order** (`ContextAssemblerPlugin.on_pre_llm_call`):

1. Budget check (typed `BudgetContract`).
2. Conversation strategy on history.
3. `collect_results("collect_context")` — DP, RAG, facets, memory bridge, etc.
4. Strategy filter + assembly into `messages[]`.
5. `post_context_assembly` for observability.

DP `on_pre_llm_call` tool-stripping runs on the **hook bus** (transform role), ideally
**before** assembler passes `available_tools` into `CollectContextRequest.metadata`
so tool names are visible to `_get_dp_instructions` while native API tools are cleared
(`PlanExecuteDP._known_tools` stash handles ordering edge cases).

---

## 27. Tool dual-channel — consolidated reference

### 27.1 Same registry, two surfaces

```
ToolContract.on_collect_tools()  →  registry
                    ├─→ ContextPart.tools()     → prompt (SYSTEM_TOOLS)
                    └─→ available_tools[]       → ModelContract.complete() schemas
```

DP is a **context provider** (`SYSTEM_PATTERN`). Tool catalog is a **separate context
provider** (`SYSTEM_TOOLS`). Neither replaces the execution catalog.

### 27.2 When each channel is active (by DP phase)

| DP / phase | Prompt catalog | `available_tools` API |
|------------|----------------|----------------------|
| ReAct DECIDE | Optional (`SYSTEM_TOOLS`) | **On** |
| Plan-Execute PLAN / REPLAN | **On** (names for JSON plan) | **Off** (`THINK_TEXT_ONLY`) |
| Plan-Execute ACT (between steps) | N/A — no LLM call | N/A — runtime `tool_call` from plan |
| Plan-Execute synthesis | Instructions only | **Off** |
| CoT / ToT THINK | As configured | Pattern-specific |

### 27.3 Target: ToolCatalogContextProvider

Recommended OSS shape (not yet default):

```python
class ToolCatalogContextProvider(ContextContract):
    def collect_context(self, request):
        tools = request.metadata.get("available_tools") or registry.collect_tools()
        return [ContextPart.tools(render_descriptions(tools), source="tool_catalog")]
```

DP then references catalog in protocol text without duplicating `_build_tools_block` logic.

---

## 28. Plan-Execute vs ReAct — phase diagram and code mapping

### 28.1 Plan-Execute sequence (target kernel)

```
PLAN (THINK, text-only)
  │  collect_context: PLAN-AND-EXECUTE protocol + tool names (SYSTEM_PATTERN / TOOLS)
  │  available_tools = []  (THINK_TEXT_ONLY)
  ▼
LLM → JSON {"plan": [{"tool": "...", "arguments": {...}}, ...]}
  │  next_action: parse plan → DPAction(tool) for step 0
  ▼
ACT loop (no LLM between steps)
  │  for each plan step: execute_contract_call("tool", ...) 
  │  on_action_result → next DPAction(tool) or synthesis flag
  ▼
on tool error (if allow_replan): REPLAN → THINK text-only → new plan
  ▼
synthesis (THINK, text-only)
  │  collect_context: synthesis instructions
  ▼
LLM → final prose → FINALIZE
```

### 28.2 ReAct sequence (target kernel)

```
loop:
  THINK (WITH_TOOLS)
    │  E_ctx → E_llm(available_tools=full catalog)
    ▼
  next_action or adapter: tool_calls? → ACT → E_tool → append tool message → OBSERVE
                              else → FINALIZE
```

### 28.3 Implementation status

| Behaviour | Plugin (`dp_plan_execute.py`) | Kernel (`RuntimeKernel` + driver) |
|-----------|------------------------------|-----------------------------------|
| Clear native tools in PLAN | `collect_context` / phase | Envelope σ₃ with DP state |
| Parse JSON plan | `next_action` | `DPOutputResolver` |
| Execute plan steps | `DPAction(action_type="tool")` | Tool symbol σ₅ |
| REPLAN on tool error | `on_tool_error` → REPLAN | DP phase transition |
| Synthesis LLM call | `_awaiting_synthesis` | Model symbol σ₄ |

**Status:** Plan-Execute runs through the same product formula as ReAct; see
`runtime/tests/test_plan_execute_plugin.py` and golden labs for parity checks.

---

## 29. Component interaction matrix — who can mutate what

Exhaustive view of **guarded resources** and **mutation authority**. Default is
deny-by-default outside listed paths.

| Component | Read | Mutate | Guarded resource | Tracking |
|-----------|------|--------|------------------|----------|
| User / task | — | Initial user turn | `messages[]` | `role=user`; session store |
| **DesignPattern** | tools list, phase, `DPState` | `collect_context` parts; `available_tools` control; `DPState.memory` | Prompt + API tools param | `mechanism=design_pattern_injection`; phase in `DPState` |
| **Memory / RAG** | query, session | `collect_context` parts; `MemoryContract` read/write | Context window; external stores | `mechanism=rag` / `inject`; memory envelope |
| **Tool catalog provider** | `collect_tools` | `SYSTEM_TOOLS` part | Prompt | `source_type=tool` |
| **ContextManager** | past turns | `manage_history` only | L1 transcript | `_summarized_turns` |
| **ContextAssembler** | all parts | Merge into `messages[]`; eviction | Full prompt | `_context_segments`, `_evicted_parts`, `context_part_contributed` |
| **Governance ⊗ⁿ** | pre-call payload | Block / modify calls | LLM, tool, memory, ctx | `governance_authorize` / `validate` events |
| **Observability ⊗ᵐ** | all symbols | Emit spans only | Telemetry | JSONL / OTel |
| **ToolContract** | — | Execute; append tool messages (via kernel) | External systems | `tool_*` envelope |
| **ModelContract** | assembled messages | LLM response | Tokens / budget | `post_llm_call` / model span |
| **SessionContract** | — | `append_turn`; `save_session` | Cross-turn L1 log | `session_id` keyed store |
| **Runtime kernel** | all | Schedule loop; invoke envelopes | Step budget | `ExecutionSession`, `AgentState` |
| **ControlContract** | signals | `INTERRUPT_SIGNAL` → DP | Loop continuation | control events |
| **SharedContext** | blackboard | KV via async API | Multi-agent coord | `source_type=shared` inject |

### 29.1 Invariants on context mutation

1. **No plugin other than assembler** writes final `messages[]` system-band composition
   (legacy `on_pre_llm_call` message mutation is deprecated).
2. **Every `ContextPart`** has `ContextProvenance` before assembly.
3. **`available_tools` changes** are control signals on the model envelope, logged by
   gov/obs even when not represented as context segments.
4. **Transcript appends** (assistant, tool) after LLM/tool calls carry call linkage
   (`tool_call_id`, `llm_call_id`) in target kernel; today partially implemented.
5. **Eviction** never silent — `_evicted_parts` + `context_compression` spans.

### 29.2 Multi-injector composition (DP + RAG + facets)

All injectors are **peers** at collect time. Ordering is by `ContextPlacement` band
then `priority` (see `context_contract.py` placement table). Conflicts are resolved by
assembly policy, not by injector precedence:

```
SYSTEM_HEADER  (identity, role)
SYSTEM_PATTERN (DP instructions)        ← DP collect_context
SYSTEM_AGENTS  (sub-agent directory)
SYSTEM_TOOLS   (tool catalog)           ← facet / tool-catalog provider
SYSTEM_SKILLS
SYSTEM_ONTOLOGY
SYSTEM_BODY
SYSTEM_MEMORY  (RAG / episodic inject)  ← MemoryContextPlugin
── conversation history (CM-filtered) ──
── current user turn ──
```

---

## 30. Per-step lifecycle — assembly, calls, annotation

### 30.1 One LLM step (end-to-end)

```
1. DP emits COLLECT_CONTEXT or THINK
2. M_ctx: CM → collect → filter → assemble → emit provenance
3. DP applies THINK_TEXT_ONLY | THINK_WITH_TOOLS on model envelope
4. E_llm: gov → model.complete(messages, tools=…) → gov validate
5. DP.next_action(llm_response) → ACT | THINK | FINALIZE | internal
6. If ACT: E_tool → append tool message → optional M_ctx post-tool collect
7. iteration_end
```

### 30.2 After LLM call — what gets written where

| Event | Written to | Provenance / notes |
|-------|------------|-------------------|
| LLM response | `messages[]` assistant turn | Model span; `post_llm_call` |
| Tool result (in-loop) | `messages[]` tool turn | Target: `mechanism=tool_call` if re-collected; tool span |
| End of `handle_task` | `SessionState` | Today: user + **final** assistant only — lightweight conversation log |
| Full tool trace across turns | Policy choice | OTel has intra-turn trace; session reload omits tool turns unless policy extended |

### 30.3 Post-tool context pass (target)

After `E_tool`, run \(M_{\text{ctx}}\) again with `step > 0` and updated `messages[]`
so tool-returned text enters the **same** provenance model as pre-LLM RAG — one semantic
path, `mechanism=tool_call`, `via=collect_context` or transcript-only if already in
`messages[]` (dedup per §26.2).

### 30.4 Hook → product mapping for context (§21 supplement)

| Legacy hook | Maps to | Includes |
|-------------|---------|----------|
| `collect_context` | `ctx_collect_execute` | DP, RAG, facets, memory |
| `on_pre_llm_call` (assembler) | `ctx_filter_*` + `ctx_assemble_*` | Full \(M_{\text{ctx}}\) |
| `on_pre_llm_call` (DP tool strip) | DP control on model envelope | `THINK_TEXT_ONLY` |
| `post_context_assembly` | `ctx_assemble_end` + obs | `_context_segments` payload |

---

## 25. Extended summary

| Question | Answer |
|----------|--------|
| Do all contracts fit? | Yes — §16 maps every export to machine, envelope, source, or boundary |
| Seamless DP swap? | Yes — ⊔ summand + §18.1 checklist; kernel must be §13 (P3) |
| ToT / Introspection? | §18 — same product, different phase graph |
| DPPhaseMachine vs DPMachine? | §17 — spec vs product adapter |
| Multi-agent labs? | §19 — \(M_{\text{coord}}\) ⊗ optional |
| Hook equivalence? | §21 — bijection to symbol sequences |
| Cleaner code? | §24 — ~150 LOC kernel, delete hook spaghetti |
| Gov / obs systematic? | §22, §24.1 — every call, all plugins, obs sees gov |
| Labs still run? | §23 — equivalence matrix + validation plan |
| Eval / pipelines? | Outside product; consume obs artifacts |
| DP as context provider? | Yes — `collect_context` / `SYSTEM_PATTERN`; §6.5, §26 |
| Tool catalog vs execution API? | Two channels — §6.4, §27 |
| Context vs working memory? | Three layers L1/L2/L3 — §6.3, §26 |
| Avoid double injection? | Dedup rules §6.3, §26.2 |
| Assembler vs CM roles? | §7, §26.3 — joint \(M_{\text{ctx}}\) |
| Plan-Execute vs ReAct? | §9.4, §28 |
| Who can mutate context? | §29 interaction matrix |
| Per-step annotation? | §30 |
| Production gaps? | §14, §28.3 — verify per-DP golden runs in CI |

The automaton is:

\[
\boxed{
M_{\text{agent}} =
\mu\,\text{turn}.\;
\mathcal{E}_{\text{ctx}}
\circ \text{sched}\bigl(M_{\text{DP}}^{(p)}\bigr)
\circ \bigl(\otimes_i M_i\bigr)
\;\;\text{with}\;\;
\forall e:\;\wrap(e)=\sigma_1\!\circ\!\cdots\!\circ\!\sigma_7
}
\]

where every contract in `mas.runtime.contracts` is either a factor \(M_i\), a source
in \(M_{\text{ctx}}\), a gov/obs summand, a ⊔ variant (DP, coord, CM), or an I/O
boundary (surface, eval pipeline) — **no exceptions**.
