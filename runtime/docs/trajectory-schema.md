<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Trajectory & Metric File Schemas

Reference for the file families produced by every MAS run:

1. **Run files** — written by `mas-runtime` under
   `$XDG_DATA_HOME/mas/runs/<mas-id>/<timestamp>-<scenario>-<run-id>/`
2. **Metric files** — written by the benchmark pipeline into
   the pipeline output directory.

The schemas are identical across use cases.

---

## Run directory layout

```
$XDG_DATA_HOME/mas/runs/<mas-id>/<YYYYMMDD-HHMMSS>-<scenario>-<run-id>/
├── run.json          # Run metadata (single object)
└── traces/
    └── events.jsonl  # Ordered stream of ObsEvents (one JSON object per line)
```

`<mas-id>` is the `id` field in `mas.yaml`.
`<run-id>` is an 8-hex-char UUID prefix generated at runtime.

---

## `run.json`

Single JSON object.  Written once at the end of the run.

```jsonc
{
  // Unique 8-hex-char identifier for this run.
  "run_id": "f52df92b",

  // MAS identifier from mas.yaml (.id field).
  "mas_id": "trip-planner",

  // Scenario name (overlay applied, e.g. "baseline", "full").
  "scenario": "baseline",

  // ISO-8601 UTC timestamp when the run started.
  "created_at": "2026-02-23T23:24:48.694866+00:00",

  // Absolute path to this run folder.
  "folder": "/home/user/.mas/runs/trip-planner/20260223-232448-baseline-f52df92b",

  // Runtime environment snapshot.
  "env": {
    "python": "3.14.3 ...",
    "platform": "macOS-26.3-arm64-arm-64bit-Mach-O",
    "packages": {
      "mas-runtime": "0.1.16"
    },
    "git_commit": "d2909f0",
    "git_dirty": true
  },

  // The user prompt fed to the entry-point agent.
  "prompt": "what trains go from Celestia to Verdantia?",

  // Overlay YAML path (relative to workspace root), if any.
  "overlay_path": "labs/lifecycle-control.lab/overlays/baseline.yaml",

  // Flavour name used for the run.
  "flavour": "local",

  // mas.yaml path (relative to workspace root).
  "mas_yaml": "library-samples/apps/trip-planner/mas.yaml",

  // CLI verbosity level.
  "verbosity": 0,

  // "success" | "error" | "timeout"
  "status": "success",

  // Wall-clock duration in seconds.
  "duration_secs": 24.87
}
```

---

## `events.jsonl`

Newline-delimited JSON.  Each line is one **ObsEvent** dict.  Events are
emitted in chronological order; `timestamp` is a Unix epoch float (seconds).

Every event carries these three mandatory fields:

| Field | Type | Description |
|---|---|---|
| `kind` | `string` | Event type — one of the `Kind.*` constants (see below) |
| `agent_id` | `string` | Emitting agent identifier (matches `agents[].id` in `mas.yaml`) |
| `timestamp` | `float` | Unix epoch seconds |
| `run_id` | `string` | Same `run_id` as in `run.json` |

### `execution_start`

Emitted when an agent begins processing a task (entry-point or recursive
delegation).

```jsonc
{
  "kind": "execution_start",
  "agent_id": "moderator",
  "timestamp": 1771889088.7677,
  "run_id": "f52df92b",

  // The input prompt / delegated task text.
  "input": "what trains go from Celestia to Verdantia?",

  // Ambient context passed from the caller.
  "context": {
    "agent_id": "moderator",
    "run_id": "local"
  }
}
```

### `execution_end`

Emitted when an agent finishes.

```jsonc
{
  "kind": "execution_end",
  "agent_id": "schedule_agent",
  "timestamp": 1771889098.2508,
  "run_id": "f52df92b",

  // "success" | "error" | "timeout"
  "status": "success",

  // The agent's final natural-language or JSON output.
  "output": "Here is the schedule information ..."
}
```

### `llm_call_start`

Emitted just before an LLM request is dispatched.

```jsonc
{
  "kind": "llm_call_start",
  "agent_id": "moderator",
  "timestamp": 1771889088.7681,
  "run_id": "f52df92b",

  // LiteLLM model name (e.g. "vertex_ai/gemini-3-pro-preview").
  "model": "vertex_ai/gemini-3-pro-preview",

  // Full messages array sent to the LLM.
  "messages": [
    { "role": "system",  "content": "You are the Trip Planner Moderator ..." },
    { "role": "user",    "content": "what trains go from Celestia to Verdantia?" }
  ],

  // Sampling parameters (null if not set).
  "temperature": null,
  "max_tokens": null
}
```

### `llm_call_end`

Emitted after the LLM response is received.

```jsonc
{
  "kind": "llm_call_end",
  "agent_id": "moderator",
  "timestamp": 1771889092.6869,
  "run_id": "f52df92b",

  // Round-trip latency in milliseconds.
  "latency_ms": 3918.59,

  // Raw LLM response.
  "response": {
    // Raw model output text (may embed JSON, tool intents, reasoning chains).
    "content": "Based on your request ...\n```json\n{\"tool_name\": \"delegate_to_schedule_agent\", ...}\n```",

    // Token counts from the provider.
    "usage": {
      "prompt_tokens": 1149,
      "completion_tokens": 157,
      "total_tokens": 1306
    }
  },

  // Provider stop reason (null when not surfaced by LiteLLM).
  "finish_reason": null,

  // Aggregate token counter (may be null; usage is canonical).
  "tokens_used": null
}
```

### `tool_call_start`

Emitted when the runtime dispatches a tool call (including delegation tools
such as `delegate_to_<agent>`).

```jsonc
{
  "kind": "tool_call_start",
  "agent_id": "moderator",
  "timestamp": 1771889092.6896,
  "run_id": "f52df92b",

  // Tool or delegation function name.
  "tool_name": "delegate_to_schedule_agent",

  // Parsed arguments dict (null when the DP has not yet extracted them).
  "arguments": null
}
```

### `tool_call_end`

Emitted when the tool returns.

```jsonc
{
  "kind": "tool_call_end",
  "agent_id": "moderator",
  "timestamp": 1771889098.2510,
  "run_id": "f52df92b",

  "latency_ms": 5561.17,
  "tool_name": "delegate_to_schedule_agent",

  // Nested result envelope from the tool / sub-agent.
  "result": {
    "result": {
      "status": "ok",
      "result": "Here is the schedule ..."
    }
  }
}
```

### `user_response`

Emitted when the entry-point agent emits its final answer to the user.

```jsonc
{
  "kind": "user_response",
  "agent_id": "moderator",
  "timestamp": 1771889113.6235,
  "run_id": "f52df92b",

  // The rendered answer.
  "content": "Here is the schedule for trains from Celestia to Verdantia ...",

  // "info" | "warning" | "error"
  "message_type": "info"
}
```

### `context_assembled`

Emitted by `ContextAssemblerPlugin` (when `emit_segments=True`, the default)
just before each LLM call.  Provides the typed segment map that corresponds to
the `messages` array in `llm_call_start`.  See `context-segmentation.md`.

```jsonc
{
  "kind": "context_assembled",
  "agent_id": "moderator",
  "timestamp": 1771889088.7681,   // same as llm_call_start that follows
  "run_id": "f52df92b",

  // Ordered list of ContextPart descriptors.
  "segments": [
    {
      "source": "SystemPromptPlugin",
      "placement": "system",
      "role": "agent_identity",
      "content": "You are the Trip Planner Moderator ..."
    },
    {
      "source": "ToolRegistryPlugin",
      "placement": "system",
      "role": "system_agents",
      "content": "Available tools: delegate_to_schedule_agent, ..."
    },
    {
      "source": "HistoryPlugin",
      "placement": "user",
      "role": "user_task",
      "content": "what trains go from Celestia to Verdantia?"
    }
  ]
}
```

### `audit`

Ad-hoc structured payload emitted by any plugin via `recorder.audit(payload)`.
Used for structured logging of non-standard events (e.g. budget gate
decisions, checkpoint saves).

```jsonc
{
  "kind": "audit",
  "agent_id": "moderator",
  "timestamp": 1771889113.62,
  "run_id": "f52df92b",

  // Arbitrary plugin-specific payload.
  "payload": {
    "event": "budget_gate_triggered",
    "total_cost_usd": 1450.0,
    "budget_limit": 1200.0
  }
}
```

---

## Multi-level trajectory view

The events above form a **nested interval tree** (see `context-segmentation.md §The Multi-Level Trajectory`):

```
MAS call:
  Agent:    execution_start(coordinator)  ───────────────────────────────── execution_end(coordinator)
              context_assembled_1 + llm_call_start_1  ── llm_call_end_1
              tool_call_start(delegate_to_worker) ────────────────────────── tool_call_end
                Agent: execution_start(worker) ──── execution_end(worker)
                  context_assembled_2 + llm_call_start_2  ── llm_call_end_2
                  tool_call_start(get_data) ── tool_call_end(get_data)
              context_assembled_3 + llm_call_start_3  ── llm_call_end_3
              user_response
```

Each `tool_call_end` at level N provides the facts available to level N-1's
next `context_assembled` event.

---

## OTel export alternative

When `instrumentation: otel_file` is set in the flavour, spans are written as
OTLP protobuf-JSON (`resourceSpans` envelope).  Eval plugins in the OSS tree
consume raw JSONL events directly; OTel span conversion is handled by
proprietary graph extensions when installed.  OTLP exports use:

```jsonc
{
  "resourceSpans": [
    {
      "scopeSpans": [
        {
          "spans": [
            {
              "name": "ToolCall",
              "startTimeUnixNano": "1771889092000000000",
              "endTimeUnixNano":   "1771889098000000000",
              "attributes": [
                { "key": "mas.agent.id",       "value": { "stringValue": "moderator" } },
                { "key": "mas.tool.name",      "value": { "stringValue": "delegate_to_schedule_agent" } },
                { "key": "mas.tool.arguments", "value": { "stringValue": "{}" } },
                { "key": "mas.tool.result",    "value": { "stringValue": "..." } }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Recognized `name` values: `ToolCall`, `LLMCall`, `AgentCall`, `TaskCall`,
`MASCall`, `RAGQuery`, `MemoryCall`, `ProcessingCall`.

OTel spans carry **both** start and end in a single record and are expanded to
an `(e_start, e_end)` event pair when converted by a proprietary graph extension.

---

## See also

- `context-segmentation.md` — theory behind segment roles and `context_assembled`
- `mas-lab/src/mas/lab/evaluation/events.py` — `Kind`, `obs_event()`
- `mas-lab/src/mas/lab/evaluation/eval_contract.py` — `MetricValue`, `MetricSpec`, `EvalContract`
