<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# LLM cache

Record and replay LLM responses via the **`llm_cache` infra middleware** —
attach a `kind: InfraMiddleware` manifest with `--infra-ref` or
`spec.infra_refs`, write responses to a JSON file, then play them back without
calling the provider.

**Reference (parameters, pipeline rules, implementation):**
[llm-cache.md](../references/llm-cache.md)

**Prerequisites:** Tutorial 0 (`task install`, `.venv` on `PATH`). Commands
below assume the **repository root** as the working directory.

---

## Overview

The **`llm_cache` middleware caches every `LLM_CALL`** the runtime makes to the
provider — initial answers, **tool-call turns** (`next_step: TOOL_CALL` /
`PARALLEL_TOOL_CALLS`), and **post-tool completions**. Each call is one cache
entry keyed by the assembled conversation preview at that point in the run.

Caching is configured in a **separate infra manifest**, not on the agent:

1. **Provider** (`standard:mock-llm`, `standard:openai`, …) — where the model runs.
2. **Cache middleware** (`middleware: llm_cache`) — read/write/replay policy and `cache_path`.
3. **Pipeline** — middleware wraps the provider; see [Pipeline order](#pipeline-order).

MAS also has a **built-in** per-agent cache (`spec.execution.cache`). When an
infra pipeline includes `llm_cache`, the built-in cache is off for that session.
See [references/llm-cache.md](../references/llm-cache.md#two-cache-mechanisms).

### End-to-end workflow (record → fixture → replay)

1. **Pick or copy infra manifests** from `library-samples/infra/` or bundled
   `standard:llm-cache-*` refs (write + replay pair, shared `cache_path`).
2. **Attach provider + write manifest** on a chat or experiment run (`--infra-ref`).
3. **Run the scenario** (single-turn or multi-step with tools). Every `LLM_CALL`
   appends to the JSON file at `cache_path`.
4. **Check in the cache file** (e.g. `library-samples/infra/cache/demo.llm-cache.json`).
5. **Replay** with the replay manifest — no provider network calls; with
   `raise_on_miss: true`, any drift from the recorded trajectory fails fast.

Optional: set `include_preview: true` on the **write** manifest so each entry
stores the conversation preview (including the user query) for manual inspection
and pruning — see [Known limitations](../references/llm-cache.md#known-limitations).

---

## Sample manifests

| Manifest | Ref / path | Purpose |
| --- | --- | --- |
| Write | `library-samples/infra/llm-cache-write.yaml` | `cache/demo.llm-cache.json` (resolved under that infra dir) |
| Replay | `library-samples/infra/llm-cache-replay.yaml` | Strict replay; same `cache_path` |
| Read+write | `standard:llm-cache` | XDG default; both read and write |
| Provider + cache | `standard:llm-proxy-cached` | `InfraBundle` (cache + OpenAI) |

Write/replay YAML lives in [library-samples/infra/](../../library-samples/README.md).
Bundled `standard:llm-cache` and `standard:llm-proxy-cached` live under
`library-standard/src/mas/library/standard/libs/standard/`.

---

## Write manifest (record)

`library-samples/infra/llm-cache-write.yaml`:

```yaml
apiVersion: infra/v1
kind: InfraMiddleware

metadata:
  name: llm-cache-write

spec:
  middleware: llm_cache
  applies_to:
    - LLM_CALL
  params:
    allow_read: false
    allow_write: true
    raise_on_miss: false
    cache_path: cache/demo.llm-cache.json
```

`allow_read: false` — always call the provider on a miss; still write responses.
Use the **same** `cache_path` in the replay manifest.

---

## Replay manifest (playback)

`library-samples/infra/llm-cache-replay.yaml`:

```yaml
apiVersion: infra/v1
kind: InfraMiddleware

metadata:
  name: llm-cache-replay

spec:
  middleware: llm_cache
  applies_to:
    - LLM_CALL
  params:
    allow_read: true
    allow_write: false
    raise_on_miss: true
    cache_path: cache/demo.llm-cache.json
```

On a hit the provider is not called. On a miss, `raise_on_miss: true` errors
instead of falling through to a live call.

Parameter reference: [references/llm-cache.md](../references/llm-cache.md#parameters-specparams).

---

## Pipeline order

Only **`InfraMiddleware`** refs add pipeline steps. **Provider refs do not** —
they only supply `api_base` / `model_access`.

Refs merge: overlay `infra_refs` → workspace → user default → CLI `--infra-ref`
(left to right). Pipeline steps append in that order; **first step = outermost**
(cache runs before the provider).

### One cache + one provider

Either CLI order works — only the middleware ref adds a pipeline step:

```bash
--infra-ref standard:mock-llm --infra-ref library-samples/infra/llm-cache-write.yaml
# same as
--infra-ref library-samples/infra/llm-cache-write.yaml --infra-ref standard:mock-llm
```

### Overlay supplies the provider

Tutorial 1's `overlays/mock-llm.yaml` adds `standard:mock-llm` via
`spec.infra_refs`. `--infra-ref library-samples/infra/llm-cache-write.yaml` merges
after the overlay → effective pipeline `[llm_cache]` wrapping the mock provider.

### Multiple middleware

Order matters — first ref is outermost:

```bash
--infra-ref standard:llm-cache --infra-ref standard:chaos-lite
```

Formal rules: [references/llm-cache.md — Pipeline model](../references/llm-cache.md#pipeline-model).

---

## Mini walkthrough (Tutorial 1 agent + library-samples infra)

This reuses the [Tutorial 1](../tutorials/01-building-an-agent/README.md) agent
and overlays — no extra files under the tutorial tree. Cache manifests come from
`library-samples/infra/`.

```bash
export PATH="$(git rev-parse --show-toplevel)/.venv/bin:$PATH"
AGENT=docs/tutorials/01-building-an-agent/agent.yaml
MOCK=docs/tutorials/01-building-an-agent/overlays/mock-llm.yaml
```

**Record**

```bash
rm -f library-samples/infra/cache/demo.llm-cache.json

mas-ctl chat "$AGENT" \
  -q "Say hello in exactly three words." \
  -o "$MOCK" \
  --infra-ref library-samples/infra/llm-cache-write.yaml \
  --single-turn
```

**Replay** (same query; swap middleware ref)

```bash
mas-ctl chat "$AGENT" \
  -q "Say hello in exactly three words." \
  -o "$MOCK" \
  --infra-ref library-samples/infra/llm-cache-replay.yaml \
  --single-turn
```

**Prove `raise_on_miss`** (different query → error)

```bash
mas-ctl chat "$AGENT" \
  -q "Say goodbye in exactly three words." \
  -o "$MOCK" \
  --infra-ref library-samples/infra/llm-cache-replay.yaml \
  --single-turn
```

---

## Live provider (OpenAI)

Requires `OPENAI_API_KEY`. Bundled refs share `$XDG_CACHE_HOME/mas/llm_cache.json`.

```bash
mas-ctl chat "$AGENT" \
  -q "Say hello in one sentence." \
  --infra-ref standard:openai \
  --infra-ref library-samples/infra/llm-cache-write.yaml \
  --single-turn

mas-ctl chat "$AGENT" \
  -q "Say hello in one sentence." \
  --infra-ref standard:openai \
  --infra-ref library-samples/infra/llm-cache-replay.yaml \
  --single-turn
```

Or `--infra-ref standard:llm-proxy-cached` for read-through caching.

---

## Tool-using runs

Every **`LLM_CALL` is cached**, including responses that schedule tools:

| Turn | Typical `next_step` | Cached? |
| --- | --- | --- |
| Model requests a tool | `TOOL_CALL` or `PARALLEL_TOOL_CALLS` | Yes |
| Model answers after tool results | `STOP` | Yes |

Each turn is a **separate cache entry** (the preview includes prior tool
results). On replay, the runtime walks the same LLM-call sequence; with
**deterministic tools** (same tool output for the same inputs), the trajectory
matches the recording and you get **cache hits on every `LLM_CALL` until the
run completes** — no live provider calls.

**Non-deterministic tool-call IDs** (common in mock mode) change the preview
text between runs, so strict replay (`raise_on_miss: true`) may miss on
post-tool turns. Prefer a **live recording** for fixture-grade replay, or
deterministic mock tools for CI.

Uses Tutorial 1's `overlays/tools.yaml` (same agent as above):

```bash
TOOLS=docs/tutorials/01-building-an-agent/overlays/tools.yaml

# Record
mas-ctl chat "$AGENT" \
  -q "Who is POTUS?" \
  -o "$MOCK" \
  -o "$TOOLS" \
  --infra-ref library-samples/infra/llm-cache-write.yaml \
  --single-turn

# Replay
mas-ctl chat "$AGENT" \
  -q "Who is POTUS?" \
  -o "$MOCK" \
  -o "$TOOLS" \
  --infra-ref library-samples/infra/llm-cache-replay.yaml \
  --single-turn
```

---

## Experiments and CI fixtures

Treat the cache file as a **run fixture**: record once, commit `cache_path`, replay
in CI with `raise_on_miss: true` so tests never hit a live LLM.

**Record:**

```bash
mas-lab benchmark run experiment.yaml \
  --infra-ref standard:mock-llm \
  --infra-ref library-samples/infra/llm-cache-write.yaml
```

**Replay:**

```bash
mas-lab benchmark run experiment.yaml \
  --infra-ref library-samples/infra/llm-cache-replay.yaml
```

There is currently **no API to stop writing mid-experiment** or to prune entries
in-process — see [Known limitations](../references/llm-cache.md#known-limitations).

See [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md).

---

## See also

- [references/llm-cache.md](../references/llm-cache.md) — exhaustive reference
- [infra.md](infra.md) — infra kinds and bundles
- [execution.md](execution.md) — built-in `spec.execution.cache`
- [Tutorial 1](../tutorials/01-building-an-agent/README.md) — agent and overlays used above
- [library-samples/README.md](../../library-samples/README.md) — sample infra manifests
