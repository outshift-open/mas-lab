<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Dataset manifest (`kind: Dataset`)

**Package:** `mas-lab-bench` · **Schema:** `dataset.schema.yaml` · **apiVersion:** `lab/v1`

A **dataset** manifest lists benchmark inputs: a user prompt (string),
optional HITL replies, memory seeds, and tool fixtures. Each **experiment**
pairs a dataset with **scenarios** and `run.n_runs`.

**Terms:** [glossary.md](../glossary.md) · **Experiment wiring:** [experiment.md](experiment.md) · **Migrating from older shapes:** [dataset-migration.md](dataset-migration.md)

```text
run = (application, flavour, memory_state, user_query)
```

The dataset declares `memory_state` and `user_query` per item.
`application` and `default_flavour` come from the experiment YAML. There is no
chat-log `turns:` field on the item.

## Table of contents

1. [Manifest format](#1-manifest-format)
2. [Item fields reference](#2-item-fields-reference)
3. [Memory seeds — the memory state slot](#3-memory-seeds--the-memory-state-slot)
4. [HITL](#4-hitl-optional)
5. [Session continuity](#5-session-continuity)
6. [Experiment-level seeds](#6-experiment-level-seeds)
7. [Seed merge order](#7-seed-merge-order)
8. [Path references](#8-path-references)
10. [`spec.source` — meta-datasets](#10-specsource--meta-datasets-mmlu-pro)

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
  app: my-app@>=v1,<v3   # omit for general-purpose datasets
  items:
    - id: "001"
      inputs:
        user: Plan a three-day trip to Paris.
```

**Flat dict** (shorthand, no kind/apiVersion required):

```yaml
name: my-dataset
items:
  - id: "001"
    inputs:
      user: Plan a three-day trip to Paris.
```

The `name` field defaults to the file stem when omitted.

### App-specific vs general-purpose

App-specific datasets live **under the app version they evaluate**. Catalog
id and `spec.app` use that same version tag:

```yaml
metadata:
  name: my-app-scenarios
  version: v1
spec:
  app: my-app@^v1    # or my-app@v1
  items: [...]
```

| Kind | On disk | Catalog id |
|------|---------|------------|
| **App-specific** | `apps/<app>/v<N>/datasets/<dataset-name>/dataset.yaml` | `<dataset-name>@vN` |
| **Unversioned app** | `apps/<app>/datasets/<dataset-name>/dataset.yaml` | `<dataset-name>` or `@v1` in `library.yaml` |
| **General-purpose** | `datasets/<name>.yaml` or `datasets/<domain>/...` | file/metadata name |

A dataset version is a **folder** (`dataset.yaml` plus optional sibling
files) next to that app version’s agents and tools.

```text
apps/<app>/v1/datasets/<name>/
  dataset.yaml                 # items: inputs + expectations
  tool_fixtures/*.yaml         # payloads listed from items
```

Each item is the run setup. `inputs.user` is the **prompt string**. Files are
`{ref: relative/path}` (on `tool_fixtures` / `memory_seeds` a bare path is
the same shorthand). Ground truth stays on the **same item** under
`expectations`.

| Slot | Role | Agent sees it |
|---|---|---|
| `inputs.user` | Prompt (string, or `{ref: file}`) | yes |
| `inputs.hitl` | Optional operator reply strings | as HITL |
| `inputs.memory_seeds` | Pre-loaded memory (prefer a sibling file) | via memory |
| `inputs.tool_fixtures` | Mapping + payloads for mock tools | via tools |
| `inputs.checkpoint.load` | Optional checkpoint path/ref used to resume this item's run; an experiment-level `checkpoints` axis overrides it when declared. | via restored session |
| `inputs.checkpoint.save` | Save checkpoint artifacts for this item when enabled (`false` by default). | no |
| `expectations` | Ground truth (`ground_truth`, `metrics`, free-form `details`) | no |

```yaml
- id: order-42-refund
  inputs:
    user: >
      Customer asks for a refund on order 42…
    tool_fixtures: {ref: tool_fixtures/order-42.yaml}
  expectations:
    ground_truth: refund approved
    details:              # owned by the app's evaluators
      order_id: 42
      action: refund
```

Long prompt in a file uses the **same** ref syntax:

```yaml
inputs:
  user: {ref: prompts/order-42-refund.txt}
  tool_fixtures: {ref: tool_fixtures/order-42.yaml}
```

Both `inputs.tool_fixtures` and `expectations` have a generic layer that
mas-lab reads and a free-form layer owned by the app. Do not mix them:

```yaml
# tool_fixtures — generic mapping: which tool gets which payload.
tool_fixtures: tool_fixtures/order-42.yaml      # every tool (same as {ref: …})
tool_fixtures:
  by_tool:
    "*": tool_fixtures/order-42.yaml            # every tool without its own entry
    query_db: tool_fixtures/db-rows.yaml
    get_weather: {city: Paris, temp_c: 18}     # inline payload
tool_fixtures:
  - tool: get_metrics
    ref: tool_fixtures/metrics.yaml
# The payload (file body or inline value) is free-form: mas-lab does not
# schema-check it, the tool does.

# expectations — generic keys + free-form details.
expectations:
  ground_truth: …        # compared by generic metrics
  metrics: [exact_match] # metrics this item is scored on
  details: {…}           # app- or tool-specific ground truth
```

An inline payload directly under `tool_fixtures` (without `by_tool`) is
rejected. Keep ground truth out of tool-fixture payloads.

Tools receive their payload through the call context, not through files or
environment variables:

```python
from mas.runtime.contracts import ToolContract, tool_fixture

class GetMetrics(ToolContract):
    def on_execute_tool(self, tool_name, arguments, *, ctx=None, **_):
        payload = tool_fixture(ctx, tool_name)  # by_tool[name], else by_tool["*"]
        ...
```

Overlay `spec.patch.params` reach tools the same way, as `ctx.runtime_params`.

### Optional schemas for the free-form parts

mas-lab does not interpret payloads or `details`, but a Dataset can declare
JSON Schemas for them in `spec.schemas`. Keys are dotted envelope paths, the
same vocabulary as [`spec.source.map`](#102-map). Only free-form roots are
allowed; the generic layer is already checked by the run-input schema.

```yaml
spec:
  schemas:
    expectations.details: {ref: schemas/booking-truth.schema.yaml}
    inputs.tool_fixtures.by_tool.get_fares: {ref: my-library:tools/get_fares.fixture.schema.yaml}
    inputs.tool_fixtures.by_tool.*.routes:            # inline schema
      type: array
  items: [...]
```

- A tool key checks the payload that tool receives: `by_tool[tool]`, else
  `by_tool["*"]` (the same rule as `tool_fixture()`).
- Items that do not provide a part are skipped. Parts without a schema are
  not checked.
- Violations, unknown keys, and missing schema files fail `Dataset.from_yaml`
  and `mas-lab validate`. `spec.source` rows are checked when materialized.
- A tool can ship its fixture schema next to its code; datasets reference it
  by catalog path.

### External datasets (meta-dataset)

See [§10](#10-specsource--meta-datasets-mmlu-pro). A Dataset YAML can
**describe how to use** a third-party corpus (`spec.source` + `map`) instead
of repeating it. `Dataset.from_yaml` materializes that into envelope items.

Bare `spec.app: <app>` means any version of that app. Omit `spec.app`
for generic datasets. `library-samples` ships one complete trip-planner
Dataset (`trip-planner-benchmark`). Cap rows in the experiment with
`dataset.limit` instead of a reduced sidecar file.

---

## 2. Item fields reference

Preferred shape is the [run-input envelope](#1-manifest-format) (`inputs` +
`expectations`). The table below is the older flat item form; migrate with
[dataset-migration.md](dataset-migration.md).

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique identifier within the dataset. Used by coupled experiments, output paths, and the run hash. |
| `inputs.user` | string, string list, or `{ref:}` | yes | The user prompt. A string is the text (never a path). A list of strings is sequential user messages. `{ref: file}` loads a sibling file. |
| `inputs.hitl` | string, string list, or `{ref:}` | no | Operator replies after the prompt, in order. |
| `inputs.memory_seeds` | list, `{ref:}`, or bare path | no | Initial memory state. See §3. |
| `inputs.tool_fixtures` | `{ref:}`, bare path, or mapping | no | Mock-tool payloads. See §1. |
| `inputs.session_id` | string | no | Fixed conversation identifier. See §5. |
| `expectations.ground_truth` | any | no | Reference answer for generic metrics. |
| `expectations.metrics` | string list | no | Metrics this item is scored on. |
| `expectations.details` | object | no | Free-form app- or tool-specific ground truth. Any other top-level `expectations` key is rejected. |
| `category` / `group` / `tags` | string / list | no | Filtering metadata. Coupled mode uses **`id` only**. |

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

Seeds can be declared inline, as `{ref: seeds/user_alice.yaml}`, or as a
bare path (shorthand on this slot only):

```yaml
# Inline
inputs:
  memory_seeds:
    - source: "user_history"
      content: "Alice visited Paris in March."

# Canonical ref
inputs:
  memory_seeds: {ref: seeds/user_alice.yaml}

# Shorthand (same meaning as {ref:} on this slot)
inputs:
  memory_seeds: seeds/user_alice.yaml
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

## 4. HITL (optional)

Most items are a single `inputs.user` string. If the run should inject
operator replies after that prompt, list them as strings:

```yaml
- id: approval
  inputs:
    user: Book a flight to Tokyo.
    hitl:
      - Operator: budget approved up to €3,000.
```

There is no `turns` list and no `{role, content}` objects in the public
YAML. Sequential user messages (rare) are a list of strings on `user`:

```yaml
- id: memory-conversation
  inputs:
    user:
      - My name is Alex and I work at Acme Corp.
      - What is my name and where do I work?
```

The runner still tags messages internally for traces; that is not an
authoring format.

### Memory + HITL

Memory seeds are injected **before** the initial `inputs.user` prompt.
The agents' memory backends are populated, then the conversation starts.
Any memory writes that happen during the conversation accumulate on top of
the seeds — this is the expected behaviour for testing stateful agents.

---

## 5. Session continuity

By default the runner generates a fresh UUID `session_id` for every run.  Set
`session_id` explicitly to:

- **Replay** a known conversation in exactly the same session slot.
- **Test session-aware memory** (e.g. `FileSessionStore`, `MemoryContextPlugin`
  keyed on `conversation_id`) with deterministic inputs.

```yaml
- id: "session-replay-001"
  inputs:
    user: Continue our last conversation.
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
  inputs:
    user: Plan my trip.
    memory_seeds: {ref: seeds/user_alice.yaml}
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
  description: Trip planner items — prompt strings, optional files, GT.
spec:
  items:

    - id: "cold-start-001"
      category: cold-start
      inputs:
        user: What are the cheapest flights from Paris to London this week?
      expectations:
        ground_truth: economy

    - id: "warm-alice-001"
      category: personalised
      inputs:
        user: Book my usual route.
        memory_seeds:
          - source: "user_preferences"
            content: "Alice always travels Paris→London, prefers 08:00 departure."
            target_agent: "concierge_agent"
          - source: "loyalty_status"
            content: "Alice: Gold tier, eligible for lounge access."

    - id: "warm-bob-001"
      category: personalised
      inputs:
        user: Book my usual route.
        memory_seeds: {ref: seeds/user_bob.yaml}

    - id: "follow-up-001"
      category: sequential-user
      inputs:
        user:
          - I need to go to Tokyo next month.
          - Make it business class.
          - What is the total cost?

    - id: "hitl-approval-001"
      category: hitl
      inputs:
        user: Book a flight to Singapore for the team offsite.
        hitl:
          - Operator: budget exception approved — up to €800 per person.
        memory_seeds: {ref: seeds/team-offsite.yaml}
        session_id: "offsite-2026-q3"

    - id: "session-recall-001"
      category: session-memory
      inputs:
        user: What did we discuss last time?
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

`spec.path` (without `items` or `source`) is a sidecar of already-shaped
items: YAML, JSONL, or CSV next to the Dataset YAML. Prefer `spec.source`
when the file is a third-party table that still needs a `map`. JSON Dataset
files are not supported — inline `spec.items` in the YAML (the 250-item
trip-planner benchmark lives in `benchmark.yaml`).

---

## 10. `spec.source` — meta-datasets (MMLU-Pro)

A **meta-dataset** is a Dataset document whose `spec.source` tells mas-lab
where a third-party corpus lives and how each row becomes one envelope item.
The YAML is the mapping. The corpus stays where it is (HuggingFace hub, a
jsonl export, a pickle from another bench).

After load, every item is the same shape as a hand-written customer-support / trip-planner
item: `id`, `inputs.user`, `expectations.*`. Experiments point at the Dataset
catalog id. Apps do not know the rows came from MMLU-Pro.

Worked copies:

- HuggingFace MMLU-Pro (no rows in git):
  [`docs/schemas/examples/datasets/mmlu-pro.yaml`](../schemas/examples/datasets/mmlu-pro.yaml)
- Offline jsonl slice (same `map`, tiny fixture):
  [`docs/schemas/examples/datasets/mmlu-pro-jsonl.yaml`](../schemas/examples/datasets/mmlu-pro-jsonl.yaml)

### 10.1 Fields

| Field | Required | Meaning |
|---|---|---|
| `kind` | yes | `huggingface` \| `jsonl` \| `csv` \| `glob` \| `pickle` |
| `id` | huggingface | Hub id, e.g. `TIGER-Lab/MMLU-Pro` |
| `split` | no | HuggingFace split (default `validation`). Slice syntax is passed through (`validation[:8]`). |
| `config` / `name` | no | HuggingFace subset name |
| `path` | jsonl/csv/pickle/glob | File or glob, relative to the Dataset folder |
| `map` | no | Column → envelope path. If omitted, defaults to `question`/`prompt`/`text`/`user` → `inputs.user` and `answer_index`/`answer`/`ground_truth`/`label` → `expectations.ground_truth` |
| `limit` | no | Keep only the first N rows (CI / smoke) |

`spec.items` may be omitted when `source` is set. If both are present,
sourced rows load first and inline items are appended (local extras).

Declare `source` on the **Dataset** manifest (preferred: a catalog id wraps
the map). `experiment.dataset.source` is the same shape and is merged on top
of the Dataset's `spec.source` at load time (override split / `limit` / `map`
for one experiment without forking the Dataset file).

### 10.2 `map`

Each key is a dotted envelope path. Each value is:

- a **column name** (`question_id`, `answer_index`), or
- a **template string** with `{column}` placeholders, or
- `{template: "…"}` / `{column: name}` (same thing, object form).

Synthesized fields (not in the raw row):

| Name | From |
|---|---|
| `options_text` | `options` list formatted as `A. …`, `B. …` |

MMLU-Pro columns used here: `question_id`, `question`, `options` (list of
strings), `answer_index` (int). Hub schema may also expose `answer` (letter)
and `category`; map those if you need them as `group` / `category` metadata.

```yaml
map:
  id: question_id
  inputs.user: "{question}\n{options_text}"
  expectations.ground_truth: answer_index
  category: category
```

### 10.3 Examples

**MMLU-Pro from HuggingFace** (requires the `datasets` package at load time):

```yaml
apiVersion: lab/v1
kind: Dataset
metadata:
  name: mmlu-pro
  version: v1
  description: Meta-dataset — maps TIGER-Lab/MMLU-Pro; does not vendor the rows.
spec:
  source:
    kind: huggingface
    id: TIGER-Lab/MMLU-Pro
    split: validation
    limit: 50
    map:
      id: question_id
      inputs.user: "{question}\n{options_text}"
      expectations.ground_truth: answer_index
```

Experiment:

```yaml
dataset:
  name: mmlu-pro@v1
# cartesian: one MAS overlay × N questions. Do not couple 12k ids.
```

**Same map, local jsonl** (no hub, no `datasets` extra):

```yaml
spec:
  source:
    kind: jsonl
    path: mmlu-pro-slice.jsonl
    map:
      id: question_id
      inputs.user: "{question}\n{options_text}"
      expectations.ground_truth: answer_index
```

**CSV:**

```yaml
spec:
  source:
    kind: csv
    path: questions.csv
    map:
      id: id
      inputs.user: question
      expectations.ground_truth: answer
```

**Glob of YAML/JSONL files:**

```yaml
spec:
  source:
    kind: glob
    path: shards/*.jsonl
    map:
      id: question_id
      inputs.user: question
      expectations.ground_truth: answer_index
```

**Pickle** (list of dicts or objects with `__dict__`, e.g. oxp-ces `QuestionModel`):

```yaml
spec:
  source:
    kind: pickle
    path: mmlu_pro_val.pkl
    map:
      id: question_id
      inputs.user: "{question}\n{options_text}"
      expectations.ground_truth: gt_answer_index
```

### 10.4 What this is not

- Not a copy of MMLU-Pro into `spec.items`.
- Not SILO-BENCH. SILO's private per-agent shards (one shard per agent, plus
  the exact ground-truth answer) are a different dataset — you cannot derive
  them from MMLU-Pro's rows, which have no private-information split.
- HuggingFace load is **not** cached as YAML in the repo. Offline CI should
  use `kind: jsonl` plus a tiny checked-in slice.

---

## Related documentation

- [dataset-migration.md](dataset-migration.md) — prompt → `inputs.user` string
- [overlay.md](overlay.md) — scenario-level memory seeds and params
- [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md) — hands-on benchmarks
