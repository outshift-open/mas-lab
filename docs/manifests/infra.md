<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Infrastructure manifests (`apiVersion: infra/v1`)

**Package:** `mas-runtime` · **Models:** `mas.runtime.manifest.infra_manifest`

**Infra** manifests declare resources the runtime resolves at execution time: LLM proxy
URLs, tool registries, secrets env mapping, OTel endpoints. Referenced from **MAS**
`infra_refs`, workspace config, or CLI `--infra-ref` — not from **overlay** business logic.

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

Provides resources: LLM endpoints, tool registries, tool servers, secrets mapping, optional
application service URLs, OTel/collector endpoints.

**Schema:** `infra.schema.yaml` (also validated via Python models in `infra_manifest.py`).

---

## Kinds

| `kind` | Purpose |
|--------|---------|
| `InfraBundle` | Compose other infra files (`spec.includes[]`); recursive merge |
| `InfraMiddleware` | Pipeline middleware (`llm_cache`, `fault_inject`) wrapped around LLM calls |
| `LLMProxy` | OpenAI-compatible proxy URL, model catalogue, defaults |
| `LLMLocal` | Local inference (e.g. Ollama) |
| `ToolRegistry` | Map logical tool-set ids → JSON tool index paths |
| `ToolServerRegistry` | tool server ids and transport |
| `PersonalSecrets` | Logical token id → env var (gitignored) |
| `Application` | Named service endpoints |
| `Infrastructure` | Legacy alias |

---

## Bundles

```yaml
apiVersion: infra/v1
kind: InfraBundle
metadata:
  name: dev-stack
spec:
  includes:
    - llm-proxy.yaml
    - otel-collector.yaml
    - tool-registry.yaml
```

Referenced from MAS `spec.infra_refs`, workspace, or CLI `--infra-ref`.

---

## Relative refs and anchor

Filesystem infra refs (for example `infra/llm-cache-write.yaml`) resolve **only**
relative to:

1. The explicit **`anchor=`** passed to `resolve_infra_refs` (typically the MAS
   or agent app root — parent of `mas.yaml` / `agent.yaml`), or
2. The discovered **workspace root** when `anchor` is omitted and
   `config.yaml` was found.

The process **working directory is not used** to locate infra YAML files. That
keeps `spec.infra_refs` tied to the application that declared them when
`mas-ctl`, benchmarks, or tests run from another directory.

Relative `cache_path` / `path` values on `InfraMiddleware` `spec.params` are
made absolute at load time relative to the **directory containing that infra
YAML file** (not CWD). See [LLM cache reference](../references/llm-cache.md).

---

## Separation from Flavour

| Infra | Flavour |
|-------|---------|
| **Where** (URLs, keys env names, registry paths) | **How** (protocol, OTel backend choice, tool-server policy) |
| Shared across flavours | Selected per deployment profile |

---

## LLM cache middleware

Record and replay LLM responses via `kind: InfraMiddleware` with
`middleware: llm_cache`. Attach with `--infra-ref` or `spec.infra_refs`.

**Guide:** [llm-cache.md](llm-cache.md) — record/replay walkthrough, manifests,
pipeline order. **Reference:** [llm-cache.md](../references/llm-cache.md).

**Pipeline order:** only `InfraMiddleware` refs add pipeline steps; provider
refs (`LLMProxy`, `standard:openai`, `standard:mock-llm`) do not. With one
cache middleware, provider and cache `--infra-ref` order is equivalent. With
multiple middleware refs, **first merged ref = outermost**. See
[llm-cache.md — Pipeline order](llm-cache.md#pipeline-order).

---

## See also

- [LLM cache](llm-cache.md) — `llm_cache` middleware guide
- [LLM cache reference](../references/llm-cache.md) — parameters, pipeline model, implementation
- [Flavour manifest](flavour.md)
- [user-config.md](../user-config.md) — workspace and `infra_refs`
- Source: `runtime/src/mas/runtime/manifest/infra_manifest.py`
