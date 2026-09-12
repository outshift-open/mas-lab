<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Execution parameters (`spec.execution`)

**Package:** `mas-runtime`, `mas-ctl` · **Schema:** `execution-binding.schema.yaml`

`spec.execution` lives on **`kind: Agent`** manifests (`agent.yaml`) and on
**overlays** that patch an agent (`spec.patch.execution`). It is execution
configuration — how the runtime engine runs a turn — not agent logic
(`spec.context`, `spec.tools`, `spec.design_pattern`, `spec.skills`).

It controls whether a turn hits a real model or a mock one, whether the LLM
response cache is consulted, whether tool calls may run in parallel, and how
large a single parallel tool batch may be before the engine queue rejects
overflow.

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

```yaml
spec:
  execution:
    mocking:
      enabled: true
    cache:
      enabled: true   # master kill-switch; omit or true to let read/write below decide
      read: true
      write: true
    parallel: true
    engine_queue_depth: 32
```

All fields are optional; every default below is what you get by omitting the
field entirely.

---

## `cache` — the LLM response cache

Every `LiveLlmEngine` call can look up a previous response before calling the
model, and store a fresh one after. This is the cache that makes offline
tutorials, CI, and golden-run fixtures deterministic and free — it is
**unrelated** to the benchmark **trace cache** described in
[Tutorial 3](../tutorials/03-experiments-and-analysis/README.md#where-traces-are-stored),
which caches whole *experiment runs*, not individual LLM calls. See
[user-config.md](../user-config.md#path-variable-reference) for both caches
side by side.

### Where it's stored

| | |
|---|---|
| Default location | `--8<-- "includes/mas-paths.md:xdg-llm-cache"` |
| Format | one JSON file, mapping a content hash of `(model, messages, tools)` to the response |
| Override (env) | `MAS_LLM_CACHE=/path/to/file.json` |
| Override (infra) | `llm_proxy.cache_path` in an `LLMProxy`/`LLMLocal` infra manifest |

Precedence for the path itself: infra `cache_path` > `MAS_LLM_CACHE` > the XDG
default above. This is the same `$XDG_CACHE_HOME/mas/…` convention the trace
and pipeline-artifact caches use — see
[user-config.md](../user-config.md#path-variable-reference).

Because the cache key includes the full `tools` schema sent to the model,
changing a tool's parameters (adding a field, renaming one) changes the hash
for every call that tool appears in, invalidating those entries. That's
expected — a schema change can change what a real model would answer.

### Controlling read and write

Reads and writes are controlled **independently** — you can replay from cache
without ever writing new entries (reproducible CI), or write fresh entries
without ever reading stale ones (force a live re-run while still recording
it).

| Control | Read | Write |
|---|---|---|
| Manifest | `spec.execution.cache.read: false` | `spec.execution.cache.write: false` |
| Env var | `MAS_LLM_CACHE_READ=0` | `MAS_LLM_CACHE_WRITE=0` |
| CLI (`mas-ctl chat`) | `--no-cache-read` | `--no-cache-write` |

Precedence, most to least specific: **CLI flag** → `spec.execution.cache.enabled`
(a hard kill-switch — `false` disables both outright, regardless of the
`read`/`write` fields) → `spec.execution.cache.read`/`write` → the env vars
above → **default `true`** for both.

```bash
# Force a live call and record it, ignoring any existing cache entry
mas-ctl chat agent.yaml -q "..." --no-cache-read

# Dry-run against cache only — never call a real model, never write
mas-ctl chat agent.yaml -q "..." --no-cache-write
MAS_LLM_CACHE_WRITE=0 mas-ctl chat agent.yaml -q "..."
```

Deleting the cache file (or pointing `MAS_LLM_CACHE` at an empty path) is
equivalent to a full cache miss — the next read populates it fresh, subject to
the write control above.

---

## `mocking`

```yaml
execution:
  mocking:
    enabled: true
```

Routes the agent to `MockModelAccess` (`standard:mock-llm` infra) instead of a
real model — no API key, no network. This is what every tutorial, golden-run
fixture, and CI run uses. See [Tutorial 0](../tutorials/00-environment-setup/README.md)
for `--infra-ref standard:mock-llm` and the `-i`/`--interactive` mock-mode
flags on `mas-ctl chat`/`run-mas`.

Mock responses are looked up the same way live ones are (the same LLM
response cache above) — with a cache miss, `MockModelAccess` falls back to a
schema-driven heuristic (pick a tool whose parameters look like the prompt
needs, or echo the prompt back) rather than calling anything real.

## `parallel`

```yaml
execution:
  parallel: false   # default: true
```

Overrides the design pattern's `parallel_tool_calls` kernel setting: whether
the model may request more than one tool call in a single turn, executed
concurrently. Set `false` to force strictly sequential tool calls regardless
of what the design pattern would otherwise allow.

## `engine_queue_depth`

```yaml
execution:
  engine_queue_depth: 32   # default: 32
```

Caps how many engine egress intents (`LLM_CALL` / `TOOL_CALL`) the kernel may
queue for **one dispatch batch** before draining them. When the model returns
more parallel tool calls than this limit, the runtime raises
`engine outbound queue full` on the overflow.

This is **not** thread-pool concurrency: `EngineWorkerPool` drains the queue
sequentially via `engine.invoke()`. The limit bounds batch size and memory for
a single model turn that schedules many tools at once (for example one script
invocation per candidate in a multi-tool reply).

| | |
|---|---|
| Manifest | `spec.execution.engine_queue_depth` (integer ≥ 1, default **32**) |
| Runtime | `KernelConfig.engine_queue_depth` → `EngineWorkerPool.max_depth` |
| Source | `runtime/src/mas/runtime/engine/worker_pool.py`, `runtime/src/mas/runtime/driver/driver.py` |

Raise the value when a legitimate workload schedules more than 32 parallel tool
calls in one turn. Lower it to fail fast on runaway tool batches.

## `max_auto_steps`

```yaml
execution:
  max_auto_steps: 512   # default: 512
```

Caps how many kernel dispatch-loop iterations (`LLM_CALL` / `TOOL_CALL` /
`HITL` round-trips) `KernelDriver` auto-advances through for **one** ingress
event (e.g. one user turn) before stopping with items still queued and
undispatched. This is a step count, not a wall-clock timeout.

| | |
|---|---|
| Manifest | `spec.execution.max_auto_steps` (integer ≥ 1, default **512**) |
| Runtime | `KernelConfig.max_auto_steps` → `KernelDriver.max_auto_steps` |
| Source | `runtime/src/mas/runtime/kernel/config.py`, `runtime/src/mas/runtime/driver/driver.py` |

Raise the value for agents whose normal workflow legitimately needs more
turns than the default — for example a multi-agent incident-triage pattern
that delegates to several specialist agents and each one may retry a failed
tool call several times before moving on. Hitting the cap does not fail the
turn outright; it stops auto-dispatch with `"max_auto_steps (N) exhausted
with M item(s) still queued and undispatched"` logged, so a run that trips
it is usually a sign the workload needs a higher budget rather than that
something is broken.

## `live` and `timeout`

Both are accepted by the schema (`live: boolean`, `timeout: number`) but are
not yet wired to runtime behavior — reserved for a future per-turn timeout /
explicit live-mode override. Setting them today has no effect.

---

## See also

- [user-config.md](../user-config.md) — XDG path reference for all MAS caches (trace, artifacts, LLM response)
- [Tutorial 3 — Experiments, Analysis & Evaluation](../tutorials/03-experiments-and-analysis/README.md) — running experiments, the trace cache
- [agent.md](agent.md) — the manifest `spec.execution` lives in
- Source: `runtime/src/mas/runtime/engine/llm_cache.py`, `runtime/src/mas/runtime/engine/worker_pool.py`, `runtime/src/mas/runtime/xdg.py`, `ctl/src/mas/ctl/session/engine_factory.py`
