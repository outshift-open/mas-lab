<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# LLM cache — reference

**Package:** `mas-runtime`, `mas-ctl` · **Schema:**
`infra-middleware-params.schema.yaml` · **Middleware id:** `llm_cache`

Exhaustive reference for the **`llm_cache` infra pipeline middleware** —
independent read/write/replay controls on `kind: InfraMiddleware` manifests.

**Hands-on guide:** [llm-cache.md](../manifests/llm-cache.md)

---

## Two cache mechanisms

MAS exposes two separate LLM response caches:

| Mechanism | Configured via | When to use |
| --- | --- | --- |
| **Built-in engine cache** | `spec.execution.cache`, `MAS_LLM_CACHE_*`, `--cache-read` / `--cache-write` on `mas-ctl chat` | Per-agent toggles — [execution.md](../manifests/execution.md#cache--the-llm-response-cache) |
| **Infra middleware cache** (this reference) | `InfraMiddleware` with `middleware: llm_cache` | Shared deployment policy, write-only recording, strict replay (`raise_on_miss`), experiments |

When `llm_proxy.pipeline` is non-empty, `build_engine` disables the built-in
`LiveLlmEngine` disk cache (`cache_active = not pipeline`). Middleware `params`
own read/write for that session — not `spec.execution.cache`.

Source: `ctl/src/mas/ctl/session/engine_factory.py`.

---

## Pipeline model

### Invoke path

```text
LLM_CALL (forward):

  ┌──────────────────┐     ┌──────────────────┐     ┌─────────────────┐
  │ LlmCacheMiddleware │ → │ LiveLlmEngine    │ → │ Provider        │
  │ (llm_cache)        │   │ (assemble + API) │   │ (OpenAI / mock) │
  └──────────────────┘     └──────────────────┘     └─────────────────┘
         ▲ miss + allow_write
         │ SHA-256(exchange_preview) → cache_path JSON
         ▼ hit + allow_read
       return MODEL_TEXT (inner never called)
```

`LlmCacheMiddleware.invoke`:

1. Skip when `not (allow_read or allow_write)` or `io.op != "LLM_CALL"`.
2. Call `exchange_preview("LLM_CALL")` **once** (side effects on correlation state).
3. On hit (`allow_read` and key in cache) → return cached `EngineIoReturn`
   (text, `TOOL_CALL`, or `PARALLEL_TOOL_CALLS` as recorded).
4. On miss with `allow_read and raise_on_miss` → `RuntimeError`.
5. Else call `inner.invoke(io)`; on `allow_write` and `MODEL_TEXT` with
   `next_step` in `{STOP, TOOL_CALL, PARALLEL_TOOL_CALLS}` → persist.

Source: `runtime/src/mas/runtime/engine/infra_pipeline.py`.

### What is cached

| `LLM_CALL` outcome | `next_step` | Written when `allow_write`? | Replayed when `allow_read`? |
| --- | --- | --- | --- |
| Final text answer | `STOP` | Yes | Yes |
| Single tool request | `TOOL_CALL` | Yes | Yes |
| Parallel tool batch | `PARALLEL_TOOL_CALLS` | Yes | Yes |

`TOOL_CALL` / `TOOL_RESULT` engine ops are **not** cached — only **`LLM_CALL`**
responses. Tool *outputs* affect the preview for subsequent `LLM_CALL` keys.

### Cache key

- **Key:** `sha256(inner.exchange_preview("LLM_CALL"))` as hex (conversation
  assembled so far, including user query and prior tool results).
- **Value:** plain string (simple `STOP` text) or structured dict (tool calls,
  parallel tools, optional `_preview` annotation).
- **File:** single JSON object at `cache_path`.
- Each agentic turn = one key. Post-tool completions are separate entries.
- Non-deterministic tool-call IDs (mock mode) change the preview between runs.

### Deterministic trajectory replay

When **tools are deterministic** (same inputs → same tool results), replaying
`LLM_CALL` over `LLM_CALL` reproduces the recorded trajectory: every turn is
a cache hit and the provider is never called until the run ends.

Requirements for strict offline replay (`raise_on_miss: true`):

1. Same `cache_path` and replay manifest as the recording.
2. Same overlays, tools, and prompts as the recording run.
3. Stable tool-call IDs in the preview (live recordings) or deterministic mocks.

### Ref merge order

Infra refs merge in this order (`merge_infra_refs`):

```text
agent / overlay spec.infra_refs
  → workspace infra_refs
  → user default_infra (if no workspace infra)
  → CLI --infra-ref flags (left to right)
```

Each ref's `pipeline` steps append via `_merge_pipeline(a, b) → a + b`.

### Pipeline wrap order

Only **`InfraMiddleware`** refs (and explicit bundle pipeline entries) append
to `llm_proxy.pipeline`. **`LLMProxy` / `LLMLocal`** refs supply provider
config only (`api_base`, `model_access`, …) — no pipeline steps.

`wrap_bidirectional_pipeline` wraps with `reversed(pipeline)`:

```text
pipeline: [ llm_cache, fault_inject ]

wrap: engine → fault_inject(engine) → llm_cache(...)

invoke: llm_cache → fault_inject → LiveLlmEngine → provider
```

**First entry in merged pipeline = outermost middleware.**

| Scenario | CLI order effect |
| --- | --- |
| One provider + one `llm_cache` ref | Order irrelevant — only middleware adds a step |
| Multiple middleware refs | First merged ref = outermost; list `llm_cache` before others |
| `InfraBundle` `spec.entries[]` | Entry order defines merge order (`standard:llm-proxy-cached`: cache before openai) |

Sources: `ctl/src/mas/ctl/workspace/config.py`, `ctl/src/mas/ctl/infra/resolve.py`,
`runtime/src/mas/runtime/engine/infra_pipeline.py`.

### `cache_path` hydration

At resolve time (`resolve_infra_refs`), for each `llm_cache` pipeline entry
with missing/empty `params.cache_path`, ctl sets:

```text
$XDG_CACHE_HOME/mas/llm_cache.json
```

(`UserConfig.cache_dir / "llm_cache.json"`). Explicit `cache_path` in the
manifest is never overwritten.

`MAS_LLM_CACHE` env var applies to the **built-in** engine cache only — not
middleware `params.cache_path`.

---

## `InfraMiddleware` manifest

```yaml
apiVersion: infra/v1
kind: InfraMiddleware

metadata:
  name: llm-cache-write

spec:
  middleware: llm_cache          # required — selects LlmCacheMiddleware
  applies_to:
    - LLM_CALL                   # default; future: TOOL_HTTP, OTEL_EXPORT
  params:
    allow_read: false
    allow_write: true
    raise_on_miss: false
    include_preview: false
    cache_path: .cache/run.llm-cache.json
```

Loaded by `_load_file` when `kind in {InfraMiddleware, InfraInterceptor}`:
`spec.middleware` → pipeline entry `middleware` id; `spec.params` → `params` dict.

Schema: `docs/schemas/runtime/fragments/infra-middleware-params.schema.yaml`.

---

## Parameters (`spec.params`)

| Param | Type | Default | Meaning |
| --- | --- | --- | --- |
| `allow_read` | boolean | `true` | Look up `cache_path` before calling the provider |
| `allow_write` | boolean | `true` | Persist `LLM_CALL` responses (`STOP`, `TOOL_CALL`, `PARALLEL_TOOL_CALLS`) |
| `raise_on_miss` | boolean | `false` | When `allow_read` and key missing, raise instead of calling provider |
| `include_preview` | boolean | `false` | On write, store `_preview` (conversation text incl. user query) per entry |
| `cache_path` | string \| null | XDG default* | JSON file path |
| `enabled` | boolean | `true` | Legacy: `false` disables both read and write (`apply_middleware` maps via `enabled` fallback) |

\* Hydrated at resolve when null/omitted — see [cache_path hydration](#cache_path-hydration).

`apply_middleware` resolution:

```python
allow_read = params.get("allow_read", params.get("enabled", True)) is not False
allow_write = params.get("allow_write", params.get("enabled", True)) is not False
raise_on_miss = params.get("raise_on_miss", False) is True
include_preview = params.get("include_preview", False) is True
```

### Cache entry format

Keys are SHA-256 hex strings. Values are either:

**Plain string** (backward compatible) — final text answer:

```json
{ "a1b2c3…": "Hello, world." }
```

**Structured dict** — tool-call or annotated entries:

```json
{
  "d4e5f6…": {
    "next_step": "TOOL_CALL",
    "tool_name": "lookup",
    "tool_arguments": {"q": "POTUS"},
    "text": "",
    "finish_reason": "tool_calls",
    "_preview": "[user]\n  Who is POTUS?"
  }
}
```

`_preview` is present only when `include_preview: true` on the write manifest.
It is ignored on read; use it to identify entries when pruning manually.

---

## Mode recipes

| Goal | `allow_read` | `allow_write` | `raise_on_miss` |
| --- | --- | --- | --- |
| Normal read-through cache | `true` | `true` | `false` |
| Record run (always hit provider) | `false` | `true` | `false` |
| Replay run (strict, no provider on miss) | `true` | `false` | `true` |
| Warm cache (no stale reads) | `false` | `true` | `false` |
| Read-only CI (never write) | `true` | `false` | `false` |

---

## `cache_path` locations

| Approach | Example | Notes |
| --- | --- | --- |
| Next to agent | `.cache/tutorial.llm-cache.json` | Relative to process CWD when file is opened |
| Repo example | `library-samples/infra/cache/demo.llm-cache.json` | Run from repository root |
| XDG default | `null` or omit | `standard:llm-cache-*` refs |
| Env `MAS_LLM_CACHE` | — | Built-in engine cache only |

Delete the JSON file to invalidate all entries. Format: `{ "<sha256-hex>": "<text>", ... }`.

---

## Bundled and example manifests

| Ref / path | `allow_read` | `allow_write` | `raise_on_miss` | `cache_path` |
| --- | --- | --- | --- | --- |
| `standard:llm-cache` | `true` | `true` | `false` | XDG |
| `standard:llm-proxy-cached` | (bundle) | — | — | cache + `standard:openai` |
| `library-samples/infra/llm-cache-write.yaml` | `false` | `true` | `false` | `library-samples/infra/cache/demo.llm-cache.json` |
| `library-samples/infra/llm-cache-replay.yaml` | `true` | `false` | `true` | same |

---

## Known limitations

| Gap | Status | Workaround |
| --- | --- | --- |
| Stop caching mid-run / mid-experiment | Not implemented | Use write manifest only on record runs; replay manifest on CI runs |
| Prune or invalidate single entries | Not implemented | Delete `cache_path` or edit the JSON manually; use `include_preview: true` to find keys |
| Human-readable query in cache file | Opt-in | `include_preview: true` stores `_preview` (includes user message) per entry |
| Built-in cache vs middleware keying | Different schemes | Do not mix built-in `spec.execution.cache` files with middleware `cache_path` |
| Mock non-deterministic tool-call IDs | Runtime behaviour | Record with live provider or deterministic mocks for strict replay |

`raise_on_miss: true` is the safeguard for **fully offline** replay: any cache
miss is a hard error, so CI never silently calls a live provider.

---

## Relation to `spec.execution.cache`

| | Built-in (`execution.md`) | Infra middleware |
| --- | --- | --- |
| Config surface | Agent / overlay `spec.execution.cache` | `InfraMiddleware` + `--infra-ref` |
| Shared across agents | No | Yes |
| `raise_on_miss` | No | Yes |
| Independent read/write | Yes | Yes (`allow_read` / `allow_write`) |
| Active when pipeline set | Disabled | **Active** |

Long term: shared runtime cache policy may move to infra/runtime manifests
([execution.md](../manifests/execution.md)).

---

## Implementation index

| Component | Path |
| --- | --- |
| Middleware | `runtime/src/mas/runtime/engine/infra_pipeline.py` — `LlmCacheMiddleware`, `apply_middleware`, `wrap_bidirectional_pipeline` |
| Serialize / deserialize | `runtime/src/mas/runtime/engine/llm_cache.py` — `middleware_cache_serialize`, `middleware_cache_deserialize` |
| Tests | `runtime/tests/test_middleware_llm_cache.py`, `runtime/tests/test_infra_pipeline_bidirectional.py` |
| Ref merge | `ctl/src/mas/ctl/infra/resolve.py` — `resolve_infra_refs`, `_merge_pipeline`, `_hydrate_pipeline_cache_paths` |
| Ref ordering | `ctl/src/mas/ctl/workspace/config.py` — `merge_infra_refs` |
| Engine wiring | `ctl/src/mas/ctl/session/engine_factory.py` — `build_engine`, `_wrap_with_infra_pipeline` |
| Session resolve | `ctl/src/mas/ctl/session/infra_resolve.py` — `resolve_session_infra` |
| Schema | `docs/schemas/runtime/fragments/infra-middleware-params.schema.yaml` |
| Bundled YAML | `library-standard/.../standard/llm-cache.yaml`, `library-samples/infra/llm-cache-*.yaml` |

---

## See also

- [llm-cache.md](../manifests/llm-cache.md) — getting started and walkthrough
- [infra.md](../manifests/infra.md) — infra kinds and bundles
- [execution.md](../manifests/execution.md) — built-in engine cache
- [user-config.md](../user-config.md) — XDG paths
