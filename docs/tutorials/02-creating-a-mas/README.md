<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 2 — Creating a Multi-Agent System

> **Packages:** `mas-ctl` (run-mas, validate), `mas-lab` (telemetry/plots)
> **Deployment:** `deployments/local-inproc.yaml` (default runtime)
> **Time:** ~30 min hands-on
> **Goal:** Compose a multi-agent trip planner with a declarative `kind: MAS` manifest and run it interactively.
> **Prerequisite:** [Tutorial 0](../00-environment-setup/) (config + infra) and
> [Tutorial 1](../01-building-an-agent/) — agent manifests and overlays.
> `mas-ctl run-mas` uses the same `default_infra` / `infra_refs` wiring as
> `mas-ctl chat` (see Tutorial 0 §2).

---

## Overview

A single agent reaches its limits when a task requires **diverse expertise**
or when **delegation** improves quality. The MAS Framework addresses this with
a declarative `kind: MAS` manifest that wires agents into a topology.

> **Standalone vs. inline:** Agents can be defined as **standalone manifests**
> (their own YAML file, imported via `ref:`) or **inline** (spec embedded
> directly in the MAS manifest). Both forms have the same expressive power.
> The trip planner uses standalone manifests for reuse and clarity.

In this tutorial you will:

1. Understand the **specialist agents** (schedule, itinerary, concierge)
2. Understand the **moderator** that delegates work
3. See how the **MAS manifest** separates agents and workflow
4. Learn how **overlays** switch topologies (single-agent, linear, broker)
5. Run the system interactively and inspect delegation traces

We use the **trip planner** — a fictional city network (the "Arborian Network")
where agents plan multi-city itineraries. The moderator delegates to three
specialists: schedule lookup, route planning, and fare estimation.

---

## The big picture

```
                       ┌──────────────────────┐
                       │     mas.yaml         │
                       │     kind: MAS        │
                       └──────────┬───────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
     ┌────────────────┐  ┌───────────────┐  ┌────────────────┐
     │ schedule_agent  │  │itinerary_agent│  │concierge_agent │
     │ (schedules +    │  │ (route plan)  │  │ (fares + costs)│
     │  attractions)   │  │               │  │                │
     └────────────────┘  └───────────────┘  └────────────────┘
              ▲                   ▲                   ▲
              └───────────────────┼───────────────────┘
                                  │ delegates_to
                       ┌──────────┴───────────┐
                       │     moderator        │
                       └──────────────────────┘
                                  ▲
                                  │ user query
                              end user
```

---

## Step 1 — The specialist agents

Each specialist is a `kind: Agent` manifest (Tutorial 1) with focused
instructions and domain-specific tools.

### Schedule agent — transport schedules & attractions

```yaml
# agents/schedule-agent/agent.yaml
apiVersion: mas/v1
kind: Agent
metadata:
  name: schedule_agent
spec:
  role:
    description: "Transport schedule and attractions specialist."
    instructions: |
      You can look up train and airplane schedules and attractions inside cities.
      Use the lookup_schedule tool to search for schedules between cities in the
      Arborian Network. Also find attractions in each city on the itinerary.
  tools:
    - ref: ../../tools/lookup_schedule.tool.yaml
  skills:
    - transport-schedule-lookup
```

### Itinerary agent — route planning

```yaml
# agents/itinerary-agent/agent.yaml
apiVersion: mas/v1
kind: Agent
metadata:
  name: itinerary_agent
spec:
  role:
    description: "Route planner and itinerary specialist."
    instructions: |
      You have access to the query_graph_database tool which queries a graph
      of cities and returns feasible paths with their travel times.
  tools:
    - ref: ../../tools/query_graph_database.tool.yaml
  skills:
    - route-planning
```

### Concierge agent — fares & costs

```yaml
# agents/concierge-agent/agent.yaml
apiVersion: mas/v1
kind: Agent
metadata:
  name: concierge_agent
spec:
  role:
    description: "Fare lookup specialist."
    instructions: |
      Use get_fares for looking up fares and calc for calculations.
      Provide a clear overview of prices for each itinerary.
  tools:
    - ref: ../../tools/get_fares.tool.yaml
    - ref: ../../tools/calc.tool.yaml
  skills:
    - fare-and-itinerary-assembly
```

> **Note:** All three agents use the ReAct pattern and `gpt-4o`.
> Each has a custom **tool** (Python function with a YAML descriptor) and
> a **skill** (knowledge documents the agent can retrieve via RAG).

---

## Step 2 — The moderator

The moderator is the **entry point** — it receives user queries and delegates
to the right specialists. It doesn't have domain tools; it has **delegation
awareness** injected by the runtime.

```yaml
# agents/moderator/agent.yaml
apiVersion: mas/v1
kind: Agent
metadata:
  name: moderator
spec:
  role:
    description: "Trip planner moderator. Coordinates schedule_agent,
      itinerary_agent, and concierge_agent."
    instructions: |
      You are a moderator coordinating a team of specialized agents.
      Based on the conversation so far, decide:
      1. If you need to call an agent, call the appropriate delegation tool
         with a clear task description. Call only one agent at a time.
      2. Make sure you use ALL agents.
      3. If you have enough information, provide a complete response that
         includes itinerary, schedule, and prices.
  skills:
    - trip-orchestration
```

> **Key difference from Tutorial 1:** The moderator doesn't use tools to
> fetch data — it uses **delegation** to other agents. The MAS topology
> (next step) defines who it can delegate to.

---

## Step 3 — The MAS manifest

The `kind: MAS` manifest wires agents into a system. It separates two
concerns into distinct YAML sections:

| Section | Purpose |
|---------|---------|
| `spec.agency.agents` | Agent refs — each has an `id` and a `ref` to its standalone manifest |
| `spec.workflow` | Topology — entry point + delegation graph |

This separation keeps **identity** (who are the agents?) apart from
**workflow** (who delegates to whom?). Each agent owns its own tools
and skills — declared in its own `agent.yaml`, not centrally.

```yaml
# mas.yaml
apiVersion: mas/v1
kind: MAS

metadata:
  name: trip-planner
  version: "0.1.0"

intent:
  summary: >
    I plan trips between cities in the Arborian Network. Tell me your
    destination preferences, travel dates, budget, and interests.

spec:
  agency:
    agents:
      - id: moderator
        ref: agents/moderator/agent.yaml
      - id: schedule_agent
        ref: agents/schedule-agent/agent.yaml
      - id: itinerary_agent
        ref: agents/itinerary-agent/agent.yaml
      - id: concierge_agent
        ref: agents/concierge-agent/agent.yaml

  workflow:
    type: dynamic
    entry: moderator
    nodes:
      - id: moderator
        delegates_to: [ schedule_agent, itinerary_agent, concierge_agent ]
      - id: schedule_agent
      - id: itinerary_agent
      - id: concierge_agent
```

### Why agents own their tools?

Each agent declares its tools and skills in its own `agent.yaml`. This
keeps agent manifests **self-contained** — you can validate, test, or
reuse an agent without the MAS manifest. The MAS only needs to know
**who** the agents are (`id` + `ref`) and **how** they interact
(`workflow`).

### The delegation graph

`workflow.type: dynamic` means the **moderator's LLM** decides delegation
order dynamically — there is no hardcoded pipeline. `delegates_to` lists the
agents the moderator is allowed to call:

```
moderator ──▶ schedule_agent
          ──▶ itinerary_agent
          ──▶ concierge_agent
```

Each delegation is a tool call (`delegate_task`) routed by the transport
plugin. The moderator's ReAct loop decides the order, frequency, and
whether to call one or all specialists.

### Topology overlays

Because the workflow lives in its own section and agents own their tools,
an overlay can switch the entire topology without touching agent
definitions. The `workflow.type` field selects the workflow strategy:

| `workflow.type` | Strategy | Who decides agent order? |
|-----------------|----------|-------------------------|
| `dynamic` | Moderator delegates dynamically | The moderator's LLM |
| `single` | One agent handles everything | N/A — no delegation |
| `sequential` | Automaton walks a fixed pipeline | Declared edge order |

**Single-agent overlay** — one generalist with all tools, no delegation:

```yaml
# overlays/single-agent.yaml
kind: Overlay
metadata:
  id: single-agent                 # ← referenced by id in experiment.yaml
  description: >
    Collapse the MAS to a single generalist agent. No delegation.

spec:
  patch:
    agents:
      - id: generalist
        ref: agents/generalist/agent.yaml

    workflow:
      type: single
      entry: generalist
      nodes:
        - id: generalist
```

**Sequential overlay** — automaton walks through specialists in order,
accumulating context at each step:

```yaml
# overlays/linear.yaml
kind: Overlay
metadata:
  id: linear                       # ← referenced by id in experiment.yaml
  description: >
    Sequential pipeline: schedule → itinerary → concierge.
    An automaton (not an LLM) drives the order.

spec:
  patch:
    agents:
      - id: schedule_agent
        ref: agents/schedule-agent/agent.yaml
      - id: itinerary_agent
        ref: agents/itinerary-agent/agent.yaml
      - id: concierge_agent
        ref: agents/concierge-agent/agent.yaml

    workflow:
      type: sequential
      entry: schedule_agent
      edges:
        - from: schedule_agent
          to: [ itinerary_agent ]
        - from: itinerary_agent
          to: [ concierge_agent ]
```

Overlays are referenced by their `metadata.id` in experiment scenarios:

```yaml
# experiment.yaml
scenarios:
  - id: single-agent
    overlays: [single-agent]       # ← references the overlay by id
  - id: linear
    overlays: [linear]
```

Overlays only touch the **agents list and workflow** — each agent's
tools and skills stay in its own manifest.

---

## Step 4 — The flavour

Flavours separate execution concerns from the agent spec. Tutorial 1
explained flavours in detail — this tutorial **does not define its own
flavour**. It inherits the workspace-root flavour at `flavours/local.yaml`.

The workspace flavour sets the LLM proxy, local emulation mode, and
telemetry defaults. `mode: local` runs all agents in-process (no network
transport between them). If a tutorial or example needs to override a specific
setting (e.g. model, embed_model), it can place a `flavours/local.yaml`
next to its `mas.yaml` — but the trip planner works with the defaults.

---

## Step 5 — Running the MAS

### Default topology (dynamic broker)

```bash
# Single query — moderator delegates to specialists dynamically
mas-ctl run-mas mas.yaml -q "Plan a 3-day trip to Thornhaven, budget €500"

# Interactive multi-turn conversation
mas-ctl run-mas mas.yaml -i
```

### Single-agent topology

One generalist agent handles everything — no delegation, no moderator:

```bash
mas-ctl run-mas mas.yaml -o overlays/single-agent.yaml \
    -q "Plan a 3-day trip to Thornhaven, budget €500"
```

### Sequential (linear) pipeline

Specialists execute in fixed order: schedule → itinerary → concierge.
An automaton drives the order, not an LLM:

```bash
mas-ctl run-mas mas.yaml -o overlays/linear.yaml \
    -q "Plan a 3-day trip to Thornhaven, budget €500"
```

### Comparing topologies

All three commands use the **same agents and tools** — only the workflow
changes. This is the power of overlays: swap topology without touching
agent definitions.

| Command | Topology | Agent(s) | Who decides order? |
|---------|----------|----------|--------------------|
| (no overlay) | `dynamic` | moderator + 3 specialists | Moderator LLM |
| `-o overlays/single-agent.yaml` | `single` | 1 generalist | N/A |
| `-o overlays/linear.yaml` | `sequential` | 3 specialists | Declared edges |

Ask: *"I want to visit Thornhaven for 3 days, budget €500, interested in history and food."*

Watch the moderator delegate:

1. → `schedule_agent`: "Find transport to Thornhaven + local attractions"
2. → `itinerary_agent`: "Plan routes between cities"
3. → `concierge_agent`: "Look up fares for the proposed routes"
4. ← Moderator assembles the final itinerary with prices

---

## Step 6 — Understanding the event stream

Every run writes `events.jsonl` to the telemetry path. Each line is a
structured event:

```json
{"event": "llm_call_start", "agent": "moderator", "timestamp": "...", "trace_id": "..."}
{"event": "delegation_start", "from": "moderator", "to": "schedule_agent", ...}
{"event": "tool_call", "agent": "schedule_agent", "tool": "lookup_schedule", ...}
{"event": "delegation_end", "from": "moderator", "to": "schedule_agent", ...}
{"event": "llm_call_end", "agent": "moderator", ...}
```

Compared to Tutorial 1's single-agent trace, a MAS trace shows
**delegation events** between agents — you can see which specialist was
called, with what task, and what it returned.

To quickly inspect the trace:

```bash
# Telemetry summary — event count, agents involved, token usage
mas-lab telemetry show logs/events.jsonl

# Interactive trajectory with delegation arrows
mas-lab plot multilevel-trajectory logs/events.jsonl --format html -o output/trajectory.html
```

> **In Tutorial 3** you'll learn how to automate this: define experiments,
> run benchmarks over datasets, build reusable analysis pipelines, and
> compare scenarios with MCEv1 evaluation.

---

## File structure

```
library-samples/apps/trip-planner/
├── mas.yaml                        # MAS manifest (kind: MAS, 4 agents)
├── agents/
│   ├── moderator/agent.yaml        # Broker — orchestrates delegation
│   ├── schedule-agent/agent.yaml   # Specialist — schedules + attractions
│   ├── itinerary-agent/agent.yaml  # Specialist — route planning
│   ├── concierge-agent/agent.yaml  # Specialist — fares + costs
│   └── generalist/agent.yaml       # Solo agent with all tools (for single-agent overlay)
├── tools/                          # Python tools + YAML descriptors
├── skills/                         # RAG knowledge documents
├── datasets/
│   └── arborian-network.yaml       # Fictional city graph (knowledge base)
└── overlays/                       # Scenario overlays (used in experiments)
```

The design-space lab (`labs/design-space.lab/`) extends this app with
pattern/topology overlays, benchmark datasets, and analysis pipelines.

---

## Scenario YAML and automated checks

`demo/scenario.yaml` records each step with commands and expected exit codes.
CI replays the offline steps:

```bash
pytest tests/tutorials/test_scenario_commands.py -v -k tuto-02
```

Live `mas-ctl run-mas` steps need `TUTORIAL_ONLINE=1` and LLM credentials (Tutorial 0).

---

## Key takeaways

1. **MAS = topology**: agents are wired by `workflow` (entry, nodes, delegation), not code
2. **Agents own capabilities**: each agent declares its own tools and skills in its `agent.yaml`
3. **Separation of concerns**: agents (nodes) and workflow (edges) are distinct YAML sections
4. **Overlays switch topologies**: a single overlay can collapse to one agent or chain into a pipeline — agent tool declarations stay unchanged
5. **Dynamic delegation**: the moderator's ReAct loop drives delegation dynamically
6. **Event stream captures delegation**: `delegation_start/end` events trace the handoff chain

---

## Going further

These docs are not required to complete this tutorial:

- [User guide](../../user-guide.md) — CLI workflows and local run patterns
- [Glossary](../../glossary.md)
- [Contributing](https://github.com/outshift-open/mas-lab/blob/main/CONTRIBUTING.md)

---

## Teaching notes (optional)

If you present this tutorial (~20 min), a useful slide arc:

1. From one agent to many — when multiple agents help
2. Delegation graph — moderator and specialists (declared in YAML, not code)
3. MAS manifest vs agent manifest — same `apiVersion` / `kind` / `spec` shape
4. Workflow types — `llm-routed`, `sequential`, `parallel`
5. Flavour decoupling — same `mas.yaml`, different runtime flavours
6. Live demo — `mas-ctl run-mas` or lab UI with delegation visible
7. Event stream — `delegation_start` / `delegation_end` in `events.jsonl`
8. Teaser — from observability to experiments (Tutorial 3)

---

## Next

→ [Tutorial 3: Experiments, Analysis & Evaluation](../03-experiments-and-analysis/) — define experiments, run benchmarks, build analysis pipelines, and compare MAS topologies with MCEv1 evaluation.
