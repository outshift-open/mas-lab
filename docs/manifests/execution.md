<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Execution parameters (`spec.execution`)

**Package:** `mas-runtime`, `mas-ctl` · **Schema:** `execution-binding.schema.yaml`

`spec.execution` is an **Agent** manifest block that controls how a turn actually
runs: whether it hits a real model or a mock one, whether the LLM response
cache is consulted, and whether tool calls can run in parallel. It does not
describe *what* the agent does (that's `spec.context`, `spec.tools`,
`spec.skills`) — only how the engine executes it.

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

## `live` and `timeout`

Both are accepted by the schema (`live: boolean`, `timeout: number`) but are
not yet wired to runtime behavior — reserved for a future per-turn timeout /
explicit live-mode override. Setting them today has no effect.

---

## See also

- [user-config.md](../user-config.md) — XDG path reference for all MAS caches (trace, artifacts, LLM response)
- [Tutorial 3 — Experiments, Analysis & Evaluation](../tutorials/03-experiments-and-analysis/README.md) — running experiments, the trace cache
- [agent.md](agent.md) — the manifest `spec.execution` lives in
- Source: `runtime/src/mas/runtime/engine/llm_cache.py`, `runtime/src/mas/runtime/xdg.py`, `ctl/src/mas/ctl/session/engine_factory.py`
