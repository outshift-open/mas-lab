<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Dataset manifest (`kind: Dataset`)

**Package:** `mas-lab-bench` · **Schema:** `dataset.schema.yaml` · **apiVersion:** `lab/v1`

A **dataset** manifest lists benchmark inputs: prompts, multi-turn dialogue, memory
seeds, and HITL fixtures. Each **experiment** pairs a dataset with **scenarios** and
`run.n_runs`; every item is executed for every scenario.

**Terms:** [glossary.md](../glossary.md) · **Experiment wiring:** [experiment.md](experiment.md)

```text
run = (mas_config, flavour, memory_state, user_query, turns)
```

The dataset declares `memory_state`, `user_query`, and `turns` per item.
`mas_config` and `flavour` come from the experiment YAML.

## Table of contents

1. [Manifest format](#1-manifest-format)
2. [Item fields reference](#2-item-fields-reference)
3. [Memory seeds — the memory state slot](#3-memory-seeds--the-memory-state-slot)
4. [Multi-turn and HITL](#4-multi-turn-and-hitl)
5. [Session continuity](#5-session-continuity)
6. [Experiment-level seeds](#6-experiment-level-seeds)
7. [Seed merge order](#7-seed-merge-order)
8. [Path references](#8-path-references)
9. [Full example](#9-full-example)

---

## 1. Manifest format

A dataset file is a YAML document.  Two formats are accepted:

**Declarative manifest** (preferred):

```yaml
apiVersion: lab/v1
kind: Dataset
metadata:
  name: my-dataset
  version: "1.0"
  description: "Trip planning evaluation items."
spec:
  items:
    - id: "001"
      prompt: "Plan a three-day trip to Paris."
```

**Flat dict** (shorthand, no kind/apiVersion required):

```yaml
name: my-dataset
items:
  - id: "001"
    prompt: "Plan a three-day trip to Paris."
```

The `name` field defaults to the file stem when omitted.

---

## 2. Item fields reference

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique identifier within the dataset.  Used in output paths, CSV rows, and the content-addressed run hash. |
| `prompt` | string | yes | The initial user message sent to the MAS entry agent. |
| `expected_answer` | string | no | Reference answer used by evaluation metrics (LLM judge, `contains`, `regex_match`, etc.). |
| `category` | string | no | Logical grouping for filtering with `dataset.filter` or `dataset.group`. |
| `turns` | list | no | Additional conversation turns after the initial `prompt`.  See §4. |
| `session_id` | string | no | Fixed conversation identifier.  See §5. |
| `memory_seeds` | list or path | no | Initial memory state injected before the run.  See §3. |
| `metadata` | any extra keys | no | All other keys are collected into `metadata` and available for filter expressions. |

---

## 3. Memory seeds — the memory state slot

### What is a seed?

A seed is a document pre-loaded into one or more agent memory backends
**before the first token is generated**.  It models the *prior state of the
world from the agents' perspective*: things they would already know before
the conversation starts.

This is conceptually the second slot of the input tuple:

```
run_input = (user_query, memory_state)
```

Without seeds the memory backend starts empty on every run (the default for
reproducible benchmarks).  Seeds let you test agents against specific
pre-existing knowledge — a user's history, a shared catalogue, a background
fact — as a first-class, versioned, reproducible input.

### Seed fields

Each seed is a dict with:

| Field | Type | Required | Description |
|---|---|---|---|
| `source` | string | yes | A logical label for the document's origin (e.g. `"user_history"`, `"product_catalog"`, `"policy"`).  Used for logging, deduplication, and content-addressing the run hash.  See note on shadowing below. |
| `content` | string | yes | The text indexed into the memory backend.  The backend embeds this text and makes it retrievable by semantic search. |
| `target_agent` | string | no | ID of the agent whose memory backend receives this seed.  When absent the seed is delivered to **all** agents. |
| `metadata` | dict | no | Arbitrary key-value pairs stored alongside the document.  Passed verbatim to `backend.index_document()`.  Useful for post-retrieval filtering (e.g. `{category: "preference", user: "alice"}`). |

### What does `source` mean?

`source` is not a file path.  It is a **human-readable provenance label** that
identifies where a piece of knowledge comes from.  Examples:

```yaml
source: "user_history"       # knowledge retrieved from a user activity log
source: "product_catalog"    # knowledge from the product database
source: "travel_policy"      # company travel rules
source: "operator_briefing"  # pre-run context injected by an operator
```

The `source` label is stored in the memory document's metadata and surfaced
in traces, so you can reason about *why* an agent retrieved a specific piece
of knowledge.

### Targeting: per-agent vs. global

```yaml
memory_seeds:
  # Per-agent: only the concierge's memory receives this
  - source: "user_preferences"
    content: "Alice prefers window seats and vegetarian meals."
    target_agent: "concierge_agent"

  # Global: ALL agents receive this (shared knowledge)
  - source: "shared_policy"
    content: "Company travel policy: economy class for flights under 3h."
```

Use `target_agent` when the knowledge is private to one agent (its own
episodic memory, its own user profile, etc.).  Omit it for facts every agent
should know — a shared catalogue, a company policy, a world-state snapshot.

### Inline list vs. path reference

Seeds can be declared inline or loaded from a separate YAML file:

```yaml
# Inline
memory_seeds:
  - source: "user_history"
    content: "Alice visited Paris in March."

# Path reference (resolved relative to the dataset file)
memory_seeds: "./seeds/user_alice.yaml"
```

The seed file may be a bare list or a dict with a `seeds`, `items`, or
`memory_seeds` key:

```yaml
# seeds/user_alice.yaml — bare list
- source: "user_history"
  content: "Alice visited Paris in March."
- source: "user_preferences"
  content: "Alice prefers boutique hotels."
```

Path references are useful when:

- Multiple dataset items share a large seed file (keep it DRY).
- Seeds are generated by a pipeline step and written to a file.
- The seed corpus is large enough to deserve its own version history.

---

## 4. Multi-turn and HITL

When a dataset item has a `turns` list, the benchmark runner keeps the same
`MasRuntime` instance alive across all turns, preserving session context
(conversation history, memory state).

```yaml
- id: "multi-turn-001"
  prompt: "Book a flight to Tokyo."      # turn 0 — sent via run_once()
  turns:
    - role: user
      content: "Actually, make it business class."   # turn 1
    - role: hitl
      content: "Operator: budget approved up to €3,000."  # HITL injection
    - role: user
      content: "Add a hotel in Shinjuku for 5 nights."    # turn 3
```

### Role semantics

| Role | Behaviour |
|---|---|
| `user` | Sent as a regular user prompt via `rt.run()`.  The agent processes it and the LLM is invoked. |
| `hitl` | **H**uman-**I**n-**T**he-**L**oop injection.  Simulates an operator stepping in.  The content is injected into the session and the agent responds to it — useful for testing approval flows, corrections, and escalation paths. |

Both roles advance the conversation; the distinction is semantic and surfaced
in traces so you can distinguish agent-driven turns from operator-driven ones.

### Memory + multi-turn

Memory seeds are injected **before turn 0** (the initial `prompt`).  The
agents' memory backends are populated, then the conversation starts.  Any
memory writes that happen during the conversation accumulate on top of the
seeds — this is the expected behaviour for testing stateful agents.

---

## 5. Session continuity

By default the runner generates a fresh UUID `session_id` for every run.  Set
`session_id` explicitly to:

- **Replay** a known conversation in exactly the same session slot.
- **Test session-aware memory** (e.g. `FileSessionStore`, `MemoryContextPlugin`
  keyed on `conversation_id`) with deterministic inputs.

```yaml
- id: "session-replay-001"
  prompt: "Continue our last conversation."
  session_id: "abc-1234-deterministic"
```

Note: a fixed `session_id` does not affect the content-addressed run hash —
the hash covers the inputs *to* the MAS, not internal session bookkeeping.

---

## 6. Experiment-level seeds

Seeds declared in the experiment YAML under `memory_seeds` are applied to
**every run** in the benchmark, regardless of the dataset item.  They model
background knowledge shared across all test cases — a product catalogue, a
company policy, a world model.

```yaml
# experiment.yaml
name: trip_planner_eval
memory_seeds:
  - source: "product_catalog"
    content: "Arborian Network schedule: Paris–London 08:00, 14:00, 20:00."
    target_agent: "transport_agent"
  - source: "company_policy"
    content: "All bookings require manager approval above €2,000."
    # no target_agent → all agents

dataset:
  path: "./datasets/trip_queries.yaml"
```

The same inline-or-path syntax is supported:

```yaml
memory_seeds: "./seeds/baseline_context.yaml"
```

---

## 7. Seed merge order

When both experiment-level and item-level seeds are present they are merged
into a single list before injection:

```
effective_seeds = experiment_seeds + item_seeds
```

**Experiment seeds come first.**  This means item seeds are indexed into the
memory backend *after* experiment seeds.  If a semantic search is run
immediately after seeding, item-specific seeds appear later in the indexing
order and will surface at higher relevance when their content is more specific
(standard embedding distance behaviour).

**Why not deduplicate by `source`?**  Deduplication by source would require
choosing one entry to keep, which implies a precedence rule that is opaque in
the YAML.  Instead the merge is intentionally additive: both documents are
indexed.  If you need to *replace* an experiment-level seed for a specific
item, use a different source name in the item seed (e.g. `"policy_override"`
instead of `"policy"`).

The merged seed list is included in the content-addressed run hash.  Two runs
that differ only in their seeds produce different hashes and are cached
independently.

---

## 8. Path references

All relative paths in a dataset file are resolved relative to **the dataset
file itself**, not the experiment YAML or the working directory.  This makes
dataset files portable: you can move an experiment directory without breaking
relative seed paths.

```
labs/my-experiment/
  experiment.yaml
  datasets/
    trip_queries.yaml          ← relative paths resolved from here
    seeds/
      user_alice.yaml
      user_bob.yaml
```

In `trip_queries.yaml`:

```yaml
- id: "alice"
  prompt: "Plan my trip."
  memory_seeds: "./seeds/user_alice.yaml"   # relative to datasets/
```

Experiment-level seeds in `experiment.yaml` are resolved relative to the
**experiment YAML file** (i.e. `labs/my-experiment/`).

---

## 9. Full example

```yaml
# labs/trip-planner-eval/datasets/trip_queries.yaml
apiVersion: lab/v1
kind: Dataset
metadata:
  name: trip-planner-queries
  version: "1.0"
  description: >
    Mixed single-turn, multi-turn, and HITL scenarios for the trip planner MAS.
spec:
  items:

    # ── Single-turn, no memory context ────────────────────────────────
    - id: "cold-start-001"
      prompt: "What are the cheapest flights from Paris to London this week?"
      category: cold-start
      expected_answer: "economy"

    # ── Single-turn with inline memory seeds ─────────────────────────
    - id: "warm-alice-001"
      prompt: "Book my usual route."
      category: personalised
      memory_seeds:
        - source: "user_preferences"
          content: "Alice always travels Paris→London, prefers 08:00 departure."
          target_agent: "concierge_agent"
          metadata: {user: "alice", type: "preference"}
        - source: "loyalty_status"
          content: "Alice: Gold tier, eligible for lounge access."
          # no target_agent → all agents receive this

    # ── Single-turn with seed file reference ─────────────────────────
    - id: "warm-bob-001"
      prompt: "Book my usual route."
      category: personalised
      memory_seeds: "./seeds/user_bob.yaml"

    # ── Multi-turn conversation ───────────────────────────────────────
    - id: "multi-turn-001"
      prompt: "I need to go to Tokyo next month."
      category: multi-turn
      turns:
        - role: user
          content: "Make it business class."
        - role: user
          content: "Add a hotel in Shinjuku for 5 nights."
        - role: user
          content: "What is the total cost?"

    # ── Multi-turn with HITL and memory seeds ────────────────────────
    - id: "hitl-approval-001"
      prompt: "Book a flight to Singapore for the team offsite."
      category: hitl
      memory_seeds:
        - source: "team_roster"
          content: "Team: Alice (Paris), Bob (London), Carol (Amsterdam). 5 people total."
          target_agent: "booking_agent"
        - source: "budget_policy"
          content: "Team offsites: approved up to €500 per person."
      turns:
        - role: user
          content: "We also need hotel rooms for 3 nights."
        - role: hitl
          content: "Operator: budget exception approved — up to €800 per person for this trip."
        - role: user
          content: "Great, proceed with the booking."
      session_id: "offsite-2026-q3"   # deterministic session for replay

    # ── Fixed session for memory continuity testing ──────────────────
    - id: "session-recall-001"
      prompt: "What did we discuss last time?"
      category: session-memory
      session_id: "test-session-recall-fixed"
```

Companion experiment YAML:

```yaml
# labs/trip-planner-eval/experiment.yaml
name: trip-planner-eval
mas:
  manifest: app: trip-planner  # resolves mas.yaml via mas.apps

# Seeds shared by every run — background world knowledge
memory_seeds:
  - source: "arborian_schedule"
    content: "Paris–London: 08:00, 14:00, 20:00. Paris–Tokyo: 11:30, 23:00."
    target_agent: "transport_agent"
  - source: "pricing_baseline"
    content: "Economy fares: Paris–London €89, Paris–Tokyo €640."

dataset:
  path: "./datasets/trip_queries.yaml"

scenarios:
  - id: baseline
    overlay: overlays/baseline.yaml
  - id: with-memory
    overlay: overlays/with-memory.yaml
```

---

## Related documentation

- [experiment.md](experiment.md) — how datasets attach to experiments
- [overlay.md](overlay.md) — scenario-level memory seeds and params
- [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md) — hands-on benchmarks
