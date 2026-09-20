<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Infrastructure manifests (`apiVersion: infra/v1`)

**Package:** `mas-runtime` · **Models:** `mas.ctl.infra.models.InfraManifest`

**Infra** manifests declare resources the runtime resolves at execution time: LLM proxy
URLs, tool registries, secrets env mapping, OTel endpoints. Referenced from **MAS**
`infra_refs`, workspace config, or CLI `--infra-ref` — not from **overlay** business logic.

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

Provides resources: LLM endpoints, tool registries, tool servers, secrets mapping, optional
application service URLs, OTel/collector endpoints.

**Schema:** `infra.schema.yaml`. Field reference for remote tools:
[ToolServerRegistry](../references/tool-server-registry.md).

---

## Kinds

| `kind` | Purpose |
|--------|---------|
| `InfraBundle` | Compose other infra files (`spec.includes[]`); recursive merge |
| `InfraMiddleware` | Pipeline middleware (`llm_cache`, `fault_inject`) wrapped around LLM calls |
| `LLMProxy` | OpenAI-compatible proxy URL, model catalogue, defaults |
| `LLMLocal` | Local inference (e.g. Ollama) |
| `ToolRegistry` | Map logical tool-set ids → JSON tool index paths |
| `ToolServerRegistry` | Remote tool-server endpoints (URL, transport, headers, timeouts) |
| `ToolProvider` | Semantic name → in-process implementation binding |
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

Referenced from workspace `config.yaml`, env `MAS_INFRA_REFS`, or CLI `--infra-ref` — not from Agent or MAS manifests.

---

## Relative refs and anchor

Filesystem infra refs (for example `infra/llm-cache-write.yaml`) resolve **only**
relative to:

1. The explicit **`anchor=`** passed to `resolve_infra_refs` (typically the MAS
   or agent app root — parent of `mas.yaml` / `agent.yaml`), or
2. The discovered **workspace root** when `anchor` is omitted and
   `config.yaml` was found.

The process **working directory is not used** to locate infra YAML files. That
keeps relative infra paths tied to the application anchor when
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
`middleware: llm_cache`. Attach with `--infra-ref` or workspace `infra_refs`.

**Guide:** [llm-cache.md](llm-cache.md) — record/replay walkthrough, manifests,
pipeline order. **Reference:** [llm-cache.md](../references/llm-cache.md).

**Pipeline order:** only `InfraMiddleware` refs add pipeline steps; provider
refs (`LLMProxy`, `standard:openai`, `standard:openai`) do not. With one
cache middleware, provider and cache `--infra-ref` order is equivalent. With
multiple middleware refs, **first merged ref = outermost**. See
[llm-cache.md — Pipeline order](llm-cache.md#pipeline-order).

---

## ToolServerRegistry

**Where** a remote tool process lives. Not the tool's advertise contract
([tool.md](tool.md)) and not which names an agent claims (`spec.providers[]`).

**Full field reference:** [tool-server-registry.md](../references/tool-server-registry.md).
Schema fragment: [`infra-tool-server.schema.yaml`](../schemas/runtime/fragments/infra-tool-server.schema.yaml).

```yaml
apiVersion: infra/v1
kind: ToolServerRegistry
metadata:
  name: mcp-localhost
spec:
  tool_servers:
    - id: localhost-mcp-tools
      transport: streamable-http
      url: http://127.0.0.1:9001/mcp
      timeout: 30
      follow_pagination: true
      cache_scope: private
      # headers:
      #   Authorization: "env:MCP_AUTH_HEADER"
```

Canonical sample: [`library-samples/infra/mcp-localhost.yaml`](../../library-samples/infra/mcp-localhost.yaml)
(defaults listed explicitly so the file is a reference, not a stub).

| Field | Default | Meaning |
|-------|---------|---------|
| `id` | required | Match overlay `providers[].name` |
| `transport` | `streamable-http` | `stdio` \| `streamable-http` \| `sse` \| `http` |
| `url` / `endpoint` | — | HTTP/SSE URL (manifest). Optional override `env:VAR\|default` |
| `command` / `args` / `env` / `cwd` | — | stdio process |
| `headers` | `{}` | Omit unless auth is needed. Secrets: `env:VAR` (unset omits the header) |
| `timeout` | `30` | Per-call timeout (seconds) |
| `follow_pagination` | `true` | Walk MCP `nextCursor` and flatten |
| `cache_ttl_ms` | omit | Client list-cache TTL in ms (`0` disables; omit caches until invalidate) |
| `cache_scope` | omit | `public` \| `private` (private keys the list cache by user) |

`--infra-ref` loads this document into `ResolvedInfra.tool_server_registry`.
Unset connection keys on `providers[]` are filled from the matching `id`.
Overlay `providers[]` may set `url`; when both overlay and infra set a key,
the overlay value is used. Prefer infra for shared endpoints.

Pair with [`library-samples/overlays/mcp-localhost.yaml`](../../library-samples/overlays/mcp-localhost.yaml)
(`kind: mcp`, `tools: "*"`).

---

## See also

- [LLM cache](llm-cache.md) — `llm_cache` middleware guide
- [LLM cache reference](../references/llm-cache.md) — parameters, pipeline model, implementation
- [ToolServerRegistry reference](../references/tool-server-registry.md)
- [Flavour manifest](flavour.md)
- [user-config.md](../user-config.md) — workspace and `infra_refs`
- Source: `ctl/src/mas/ctl/infra/models.py`
