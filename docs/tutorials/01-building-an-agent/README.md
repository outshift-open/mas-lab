<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 01 — Building an Agent

## Quick commands

HITL is **declarative** via `spec.governance` in an overlay — there is no `--hitl` CLI flag.

From this directory (`docs/tutorials/01-building-an-agent`):

```bash
# Live chat with tools
mas-ctl chat agent.yaml \
  -o overlays/tools.yaml \
  -o overlays/skills.yaml \
  -o overlays/memory.yaml \
  -q "What is the current price of Apple?"

# HITL — governance overlay sets hitl_on_tool + hitl_mode: interactive
mas-ctl chat agent.yaml \
  -o overlays/tools.yaml \
  -o overlays/governance-hitl.yaml \
  -q "What is the current price of Apple?"

# Offline HITL demo (no live LLM) — mock-llm overlay
mas-ctl chat agent.yaml -i \
  -o overlays/tools.yaml \
  -o overlays/mock-llm.yaml \
  -o overlays/governance-hitl.yaml

# Operator steering mid-run (interactive session)
mas-ctl chat agent.yaml -i -o overlays/tools.yaml --trace
# then type: /steer Use web search for stock prices, not fruit.

# TUI — same manifest/overlays
mas-ctl tui agent.yaml \
  -o overlays/tools.yaml \
  -o overlays/governance-hitl.yaml
```

Deployment: `deployments/local-inproc.yaml` (default runtime).

---

> **Packages:** `mas-ctl` (chat/validate), `mas-runtime` (contracts/plugins), `mas-lab` (plots/benchmarks)
> **Time:** ~30 min hands-on
> **Goal:** Go from an empty YAML file to a working QA agent with tools, a skill, and memory — then run it via CLI and API.
> **Prerequisite:** complete [Tutorial 0](../00-environment-setup/) first. It
> covers `task install`, `$XDG_CONFIG_HOME/mas/config.yaml`, infra bundles, data/trace cache
> paths, and API keys.  Offline validation steps run without an LLM; live runs
> need `default_infra` or `--infra-ref` plus `OPENAI_API_KEY` in `.env`.

---

## Overview

The MAS Framework defines agents declaratively. An agent manifest is a YAML file
(`kind: Agent`) that describes *what* the agent does — not *how* it does it.
The runtime handles the rest: design pattern execution, tool invocation,
context management, observability.

In this tutorial you will:

1. Write a **minimal agent manifest** (3 fields) and run it
2. Add **tools** via an **overlay** — no manifest duplication
3. Stack a **skill** overlay on top
4. Stack **memory** + **event tracing** — see the agent think in real time
5. Explore the CLI modes
6. Serve the agent card via HTTP
7. Inspect the **trace**: raw `events.jsonl` → trajectory / multilevel plots

Each step adds an `--overlay` to the CLI command — the base `agent.yaml`
never changes.

Every step builds on the previous one — you can stop at any point and have a
working agent.

---

## Step 1 — The minimal manifest

This is `agent.yaml` — the base manifest for the entire tutorial:

```yaml
apiVersion: mas/v1
kind: Agent

metadata:
  name: qa-agent

spec:
  context:
    intent: "Answer general knowledge questions."
    role: |
      Answer questions clearly and concisely.
```

That's it. Everything else has sensible defaults:

| Field | Default | Meaning |
|-------|---------|---------|
| `spec.models[0].model` | `gpt-4` (overridden by flavour) | Main LLM — works without flavour; flavour overrides |
| `spec.design_pattern.type` | `react` | ReAct loop — up to **25 steps** per turn |
| `spec.context_manager.type` | `sliding-window` | Keep last **20 turns** in context |

> **Key insight:** The manifest is a *specification*, not a configuration file.
> It declares the agent's capabilities and intent. The runtime resolves how
> to execute it based on the active **flavour** (local, mock, cloud…).

### How the runtime connects the manifest to an LLM

Four layers separate concerns:

```
 agent.yaml           flavour/local.yaml        infra/                .env.local
 ┌──────────┐         ┌──────────────┐          ┌──────────────┐      ┌──────────┐
 │ WHAT      │         │ HOW           │          │ WHERE         │      │ SECRET   │
 │ model     │         │ protocol      │          │ model serving │      │ API key  │
 │ context   │         │ plugins       │          │ tool providers│      │ value    │
 │ tools     │         │   → infra ref │          │ OTel collector│      │          │
 └──────────┘         └──────────────┘          └──────────────┘      └──────────┘
 (agent identity)      (deployment profile)      (providers)            (personal)
```

- **Agent** — *what* it does: model (`gpt-4o-mini`), context, tools, plugins
- **Flavour** — *how* it's deployed: protocol + plugins (local in-process vs remote agent-remote). Infra refs come from workspace/CLI, not the flavour
- **Infrastructure** — *where* services are: model proxy endpoint, tool providers, OTel collector
- **Credentials** — the secret value (API key) in `.env.local`, never committed

The model name in the manifest (`gpt-4o-mini`) is a **canonical name** — it never
changes regardless of which cloud backend is used. Infrastructure maps it to the
wire name (`gpt-4o-mini`, `vertex_ai/...`, etc.) at startup.
Tools and skills are resolved by proximity: the runtime looks for them next to
the manifest first, then falls back to the standard library.

This tutorial ships two flavours — same agent, different postures:

```yaml
# flavours/local.yaml — development
spec:
  protocol:
    mode: local                    # in-process — no network calls
  telemetry:
    backend: file                  # lightweight file-based traces
    path: logs/
```

```yaml
# flavours/prod.yaml — production-like
spec:
  agent_comm:
    protocol: local                 # in-process delegation (MAS topology)
    mode: remote
  tools:
    remote_tools_enabled: true              # tools served via tool servers
    allowed: [web-search, calculator, memory-search]
  telemetry:
    backend: otlp                  # OpenTelemetry (vs file)
  observability:
    trace_content: false           # don't log prompt content
```

The agent manifest is identical in both cases — only the deployment changes.

Before a **live** LLM run, set your API key (Tutorial 0 §4):

```bash
# At repo root or tutorial directory
echo 'OPENAI_API_KEY=sk-…' >> .env    # gitignored — never commit
source .env
```

With `default_infra: standard:production` in `$XDG_CONFIG_HOME/mas/config.yaml`, you do not
need `--infra-ref` on every command.  Use `--flavour mock` for offline runs.

### Run it

First, validate the manifest against the schema:

```bash
cd docs/tutorials/01-building-an-agent
mas-ctl validate agent.yaml
```

Then run a single query:

```bash
mas-ctl chat agent.yaml -v -q "What is the capital of France?"
```

Or start an interactive REPL (type `quit` to exit):

```bash
mas-ctl chat agent.yaml -i
```

### What happened

The runtime loaded the manifest, resolved the `local` flavour, loaded
infrastructure (model provider, tool provider), instantiated the default
ReAct design pattern, and ran a single-turn LLM call.  No tools were declared
yet, so the ReAct loop short-circuited to a direct answer.

---

## Step 2 — Adding tools via overlay

Instead of editing `agent.yaml`, we **overlay** new capabilities on top.
An overlay is a partial manifest that merges into the base — only the fields
you declare are changed; everything else stays. The `--overlay` flag applies it:

Validate the overlay first:

```bash
mas-ctl validate agent.yaml -o overlays/tools.yaml
```

Then run:

```bash
mas-ctl chat agent.yaml -v \
  -o overlays/tools.yaml \
  -q "If Tokyo has 14 million people and Paris has 2.1 million, how many times larger is Tokyo?"
```

`overlays/tools.yaml` adds tools and updates the role instructions:

```yaml
# overlays/tools.yaml
spec:
  context:
    role: |
      Answer questions clearly and concisely.
      When you need to perform calculations, use the calculator tool.
      When you need current information from the web, use the web_search tool.

  tools:
    - web-search
    - calculator
```

Tools are referenced by **semantic name** — `web-search`, `calculator`. The
runtime binds them to actual Python modules or tool servers at startup; the
agent manifest never references implementation details.

The ReAct loop now has two tools. With `-v` you see the exchange:

```
[qa-agent] AGENT -> TOOL (calculator): {'expression': '14000000 / 2100000'}
[qa-agent] TOOL (calculator) -> AGENT: {'result': 6.666...}
```

---

## Step 3 — Stacking a skill overlay

Skills are markdown documents that give the agent domain expertise.
They are referenced by **semantic name** — just like tools — and resolved
via proximity search (`skills/` next to the manifest → `mas.library.standard/skills/`).

```yaml
# overlays/skills.yaml
spec:
  skills:
    - answer-formatting
```

The runtime finds `skills/answer-formatting/SKILL.md` automatically.
No `skills_dir` needed.

Stack it on top of the tools overlay with a second `--overlay`:

```bash
mas-ctl validate agent.yaml \
  -o overlays/tools.yaml -o overlays/skills.yaml

mas-ctl chat agent.yaml -v \
  -o overlays/tools.yaml \
  -o overlays/skills.yaml \
  -q "Who is the current president of the United States?"
```

> **Overlays are applied left-to-right.** Each one merges into the result
> of the previous merge. The base `agent.yaml` is never modified.
> Fields declared in a later overlay win over earlier ones; list fields (tools, skills) are appended.

The agent now follows the formatting rules from
`skills/answer-formatting/SKILL.md` — you'll see the structured answer
format with confidence indicator.

---

## Step 4 — Adding memory

Memory is a **resource**, not a tool.  The agent accesses it through
two paths: proactive context injection (RAG) and reactive tool calls.
This tutorial covers the practical setup end-to-end.

Like tools and skills, memory is declared by **name** — the runtime resolves
the right plugin bundle:

```yaml
# overlays/memory.yaml
spec:
  memory: semantic    # ephemeral (in-memory) — no filesystem dependency

  tools:
    - memory-search       # exposes memory_search, memory_get, memory_store
```

Two memory modes are available:

| Name | Storage | Use when |
|------|---------|----------|
| `semantic` | In-memory (`:memory:`) | Tests, benchmarks, CI — each run starts clean |
| `semantic-persistent` | `$XDG_DATA_HOME/mas/memory/{agent_id}.sqlite` | Interactive demos where memory must survive across sessions |

Both wire the same **SemanticMemoryPlugin** — hybrid search (vector + FTS),
proactive RAG injection into the user message, and the `memory-search` tool
provider (`memory_search`, `memory_get`, `memory_store`).  The only
difference is whether the SQLite database lives on disk or vanishes when
the process exits.

The demo below uses ephemeral memory (`semantic`) — Run 1 shows HITL
correction within a session, Run 2 uses a **seed overlay** to pre-populate
memory at startup.

Stack all three overlays:

```bash
mas-ctl validate agent.yaml \
  -o overlays/tools.yaml -o overlays/skills.yaml \
  -o overlays/memory.yaml

mas-ctl chat agent.yaml -v \
  -o overlays/tools.yaml \
  -o overlays/skills.yaml \
  -o overlays/memory.yaml \
  -q "What is the current price of Apple?"
```

The `-v` flag prints each agent operation to stderr (LLM calls, tool
round-trips, latencies):

```
  [qa-agent] AGENT -> TOOL (web_search): {'query': 'current price apples'}
  [qa-agent] TOOL (web_search) -> AGENT: {'results': [...]} (1205ms)
```

### Run 1 — HITL: Ambiguous question → Correction + Memory store

Memory is **ephemeral** by default (in-memory SQLite) — each process starts
clean with no filesystem dependency.

```bash
mas-ctl chat agent.yaml -v \
  -o overlays/tools.yaml \
  -o overlays/skills.yaml \
  -o overlays/memory.yaml \
  -q "What is the current price of Apple?" \
  -q "No, I meant Apple the fruit, not the stock. Remember this for next time."
```

**Turn 1 — The ambiguous question (empty memory):**

```
You: What is the current price of Apple?
```

The agent interprets "Apple" as the stock (AAPL) — common LLM behaviour
with no prior context:

```
  🤖 llm call → gpt-4o-mini (2 messages)
  🔧 tool call → web_search({'query': 'current price of Apple stock'})
  ✓ web_search → {'summary': 'Stock Price - Apple: ... $258.83 ...'}
Agent: The current price of Apple Inc. (AAPL) stock is approximately $258.83.
```

**Turn 2 — The user corrects and the agent stores to semantic memory:**

```
You: No, I meant Apple the fruit, not the stock. Remember this for next time.
```

The agent calls `memory_store` to record the correction:

```
  🔧 tool call → memory_store({
      'content': "User prefers information about Apple the fruit ...",
      'source': 'user_preference'
    })
  ✓ memory_store → {'status': 'stored', 'doc_id': '3b7c6427...'}
Agent: Got it! I'll remember that you're asking about apple the fruit.
```

Since memory is ephemeral, the stored preference vanishes when the
process exits.  Run 2 shows how to **pre-seed** that knowledge into a
fresh process.

### Run 2 — Pre-seeded memory, single shot (new process)

A seed overlay pre-populates semantic memory at startup — same effect as
if the agent had learned the preference in a previous session:

```yaml
# overlays/memory-seed.yaml
spec:
  memory_seed:
    - source: user_preference
      content: >
        User always refers to the fruit when asking about 'Apple',
        not the stock.
```

Stack it on top of the memory overlay:

```bash
mas-ctl chat agent.yaml -v \
  -o overlays/tools.yaml \
  -o overlays/skills.yaml \
  -o overlays/memory.yaml \
  -o overlays/memory-seed.yaml \
  -q "What is the current price of Apple?"
```

The `SemanticMemoryPlugin` proactively injects the seeded preference into
the user message *before the LLM sees it*:

```
  → LLM sees: "[Relevant memories — apply these before answering]
               - User always refers to the fruit when asking about 'Apple' ...
               What is the current price of Apple?"
  🔧 tool call → web_search({'query': 'current price of Apple fruit'})
Agent: The current price of apple fruit is approximately $1.56 per pound.
```

**The proof:** same question as Turn 1 of Run 1, opposite answer —
in a brand new process with zero conversation history.
The seeded memory resolved the ambiguity on the **first turn**.
Without the seed overlay, the agent defaults to stock (as seen in Run 1).

> For cross-session persistence (memory survives across processes), use
> `memory: semantic-persistent` — stores at `$XDG_DATA_HOME/mas/memory/{agent_id}.sqlite`.
> See the [memory modes table](#step-4--adding-memory-and-event-tracing) above.

> For deeper implementation details on runtime behavior and manifests,
> see the local docs listed in the "Going further" section below.

---

## Step 5 — Running via CLI

You've already used `-q` for single queries and multi-turn scripted
conversations.  Here are the other modes:

### Interactive REPL

```bash
mas-ctl chat agent.yaml -i \
  -o overlays/tools.yaml \
  -o overlays/skills.yaml
```

Tool exchanges are printed automatically in interactive mode.

### Single query with pipe

```bash
echo "What is the GDP of France?" | mas-ctl chat agent.yaml -v
```

### With a different flavour

```bash
# Offline / no API key needed — cached LLM responses from artifacts/llm_cache.json
mas-ctl chat agent.yaml -i -o overlays/mock-llm.yaml

# Production-like: agent-remote transport, tool servers, OTel telemetry
mas-ctl chat agent.yaml -i  # use workspace flavour / infra for prod-like runs
```

Flavour names are resolved by **proximity** — `--flavour prod` finds
`flavours/prod.yaml` next to the manifest.  `mock` is a built-in
flavour that serves responses from a SHA-256-keyed JSON cache
(`artifacts/llm_cache.json`), so you can run the tutorial without
network access.

The agent manifest is the same in all cases — only the deployment
posture changes.

### CLI-only agent (no YAML)

You can also add tools, skills, memory, and plugins directly from the
command line — useful for quick experiments without writing any YAML files:

```bash
mas-ctl chat agent.yaml -v -i \
  --tool web-search \
  --tool calculator \
  --skill answer-formatting \
  --memory semantic \
  --plugin mas.runtime.plugins.event_log_plugin:EventLogPlugin
```

This is equivalent to stacking `overlays/tools.yaml`, `overlays/skills.yaml`,
and `overlays/memory.yaml` — plus an `EventLogPlugin` for emoji-prefixed
event tracing (`▶`, `🔧`, `✓`, `◼`).

| Flag | Effect |
|------|--------|
| `--tool NAME` | Add a tool by semantic name (repeatable) |
| `--skill NAME` | Add a skill by name (repeatable) |
| `--memory NAME` | Enable a memory backend (`semantic`, `semantic-persistent`) |
| `--plugin MOD:CLS` | Load a plugin by module path and class (repeatable) |
| `--set KEY=VALUE` | Set a `spec.context` key (repeatable) |

CLI flags are applied **after** all `--overlay` files, so they can override
or extend any overlay.

---

## Overlay progression

One base manifest, overlays stacked with `--overlay`:

| Step | Command | What's new |
|------|---------|------------|
| 1 | `agent.yaml` alone | Minimal: `context.intent` + `context.role` |
| 2 | `+ overlays/tools.yaml` | + tools: `web-search`, `calculator` |
| 3 | `+ overlays/skills.yaml` | + skills: `answer-formatting` |
| 4 | `+ overlays/memory.yaml` | + memory resource (plugin) + context injection + `memory-search` tool |

The file `agent-final.yaml` shows what the runtime sees after merging all four
overlays — a single assembled view for reference. Validate it:

```bash
mas-ctl validate agent-final.yaml
```

---

## Scenario YAML and automated checks

This tutorial ships `demo/scenario.yaml` — a structured walkthrough with
commands and expected exit codes.  CI runs the offline steps automatically:

```bash
# From repository root
pytest tests/tutorials/test_scenario_commands.py -v -k tuto-01
```

Live `mas-ctl chat` steps need `TUTORIAL_ONLINE=1` and a configured LLM (Tutorial 0).

---

## Key takeaways

1. **Spec-first**: define *what* the agent does, not *how*
2. **Defaults matter**: ReAct, sliding-window, model — you get a capable agent with 3 fields
3. **Overlays compose**: `--overlay` stacks features without duplication
4. **Tools by name**: the agent says `web-search`; the runtime binds it to a Python module or tool server — the agent manifest never sees implementation details
5. **Skills are markdown**: domain knowledge injected into the system prompt
6. **Memory is a resource, not a tool**: two access paths (proactive RAG injection + `memory_search` tool) share the same plugin
7. **Flavours separate deployment from identity**: `local` (in-process, file traces) vs `prod` (gRPC, tool-server, OTel) with zero manifest changes
8. **CLI flags**: same manifest — `-q` for scripted queries, `-i` for interactive REPL

---

## Step 7 — Inspecting the trace

Every agent run writes structured events to `events.jsonl` (configured by the
flavour's `telemetry.path`). This is raw observability data — let's turn it
into something useful.

### 7a — The raw event stream

After running the agent with the memory overlay (Step 4), look at the log:

```bash
cat logs/events.jsonl | head -5
```

```json
{"event": "llm_call_start", "agent": "qa-agent", "timestamp": "2026-04-19T14:22:01Z", "trace_id": "abc123"}
{"event": "tool_call_start", "tool": "web-search", "args": {"query": "square root of 729"}, "agent": "qa-agent"}
{"event": "tool_call_end", "tool": "web-search", "duration_ms": 120}
{"event": "llm_call_end", "agent": "qa-agent", "tokens": {"in": 450, "out": 82}}
{"event": "session_end", "agent": "qa-agent", "total_tokens": 532}
```

Each line is a self-contained JSON event with the agent name, timestamp,
trace ID, and event-specific payload. The `dp_state` field (when present)
captures the design pattern's internal state — which ReAct iteration,
think/act/observe phase, and reasoning text.

### 7b — Trajectory diagrams

> **Knowledge-graph normalization** (`mas-lab graph normalize`, Neo4j push,
> structural validation) is not part of this open-source repository. OSS
> tutorials plot trajectories directly from `events.jsonl`.

Render the event stream as a visual trajectory:

```bash
# Mermaid (text — paste into any Mermaid renderer)
mas-lab plot trajectory logs/events.jsonl --format mermaid

# SVG file
mas-lab plot trajectory logs/events.jsonl --format svg -o output/trajectory.svg

# Interactive HTML
mas-lab plot trajectory logs/events.jsonl --format html -o output/trajectory.html
```

```mermaid
sequenceDiagram
    actor User
    participant qa-agent
    User->>qa-agent: What is the square root of 729, and is the result prime?
    qa-agent->>qa-agent: 🔧 calculator(sqrt(729)) → 27
    qa-agent-->>User: The square root of 729 is 27. 27 is not prime (3 × 9).
```

> **This is what you'll automate in Tutorial 3** — experiments define
> pipelines that extract trajectories and generate plots for every run
> automatically.

---

## Going further

These docs are not required to complete this tutorial — read them when you
want to understand the underlying mechanics:

- [Glossary](../../glossary.md) — manifest vocabulary
- [User guide](../../user-guide.md) — install and CLI workflows
- [Contributing](https://github.com/outshift-open/mas-lab/blob/main/CONTRIBUTING.md) — extension points

---

## Teaching notes (optional)

If you present this tutorial (~20 min), a useful slide arc:

1. Motivation — declarative agents vs imperative frameworks
2. Minimal manifest — three fields and sensible defaults
3. Tool declaration — `kind: Tool` spec vs Python `impl`
4. Live ReAct demo
5. Progressive enrichment — tools → skills → memory
6. Agentic memory — Apple ambiguity example across two runs
7. Contracts and control — kernel ingress/egress (see Mealy guide)
8. CLI vs API — same manifest, `--serve-oasf`
9. Teaser — multiple agents (Tutorial 2)

---

## Next

→ [Tutorial 2: Creating a Multi-Agent System](../02-creating-a-mas/) — compose a 4-agent trip planner MAS with tool/skill catalogs, routing topology, and overlay-driven topology switching.
