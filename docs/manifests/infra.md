<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Infrastructure manifests (`apiVersion: infra/v1`)

**Package:** `mas-runtime` · **Models:** `mas.ctl.infra.models.InfraManifest`

**Infra** manifests declare resources the runtime resolves at execution time: LLM proxy
URLs, tool registries, secrets env mapping, and OTel endpoints. Resolved from workspace
configuration or CLI `--infra-ref`; `infra_refs` is not a field on Agent, MAS, or
Overlay manifests.

**Terms:** [glossary.md](../glossary.md) · Hub: [README.md](README.md).

Provides resources: LLM endpoints, tool registries, tool servers, secrets mapping, optional
application service URLs, A2A agent endpoints, and OTel/collector endpoints.

**Schema:** `infra.schema.yaml`. Field reference for remote tools:
[ToolServerRegistry](../references/tool-server-registry.md).

---

## Kinds

| `kind` | Purpose |
| -------- | --------- |
| `InfraBundle` | Compose other infra files (`spec.includes[]`); recursive merge |
| `InfraMiddleware` | Pipeline middleware (`llm_cache`, `fault_inject`) wrapped around LLM calls |
| `InfraInterceptor` | Cross-cutting middleware reference with explicit applicability |
| `LLMProxy` | OpenAI-compatible proxy URL, model catalogue, defaults |
| `LLMLocal` | Local inference (e.g. Ollama) |
| `ToolRegistry` | Map logical tool-set ids → JSON tool index paths |
| `ToolServerRegistry` | MCP endpoint for consuming/deploying, or local tool/skill paths (`protocol: local`) |
| `ToolProvider` | Semantic name → in-process implementation binding |
| `PersonalSecrets` | Logical token id → env var (gitignored) |
| `Application` | Named service endpoints |
| `Datastore` | Named data-store connections |
| `SecretsProvider` | Secrets backend configuration |
| `RuntimeEngine` | Runtime execution policy; see [runtime-engine.md](runtime-engine.md) |
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

Referenced from workspace `config.yaml` or CLI `--infra-ref` — not from Agent or MAS manifests.

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

## A2A agent endpoints

An `Application` infra manifest can name external agent endpoints without putting
deployment URLs in the MAS topology:

```yaml
apiVersion: infra/v1
kind: Application
metadata:
  name: a2a-agents-local
spec:
  endpoints:
    weather-oracle:
      url: http://127.0.0.1:9005
```

Reference the endpoint from an agency entry:

```yaml
spec:
  # Configure this file through workspace config or --infra-ref.
  agency:
    agents:
      - id: weather-oracle
        # The agency only names weather-oracle; infra matches by that name.
        # ref is omitted because this is an external dependency.
```

The current resolver is static and manifest-based. Directory discovery and
search/composition are intentionally separate future plugins.

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

## CLI overrides

Resolved infrastructure can be addressed with the same root-qualified syntax:

```bash
mas-ctl chat agent.yaml \
  --override 'infra:spec.tool_servers[id=mcp].port=9100'
```

The effective in-memory infrastructure is patched; the referenced YAML file is
not modified.

For reusable Infra changes, use an Overlay with `target.kind: Infra` and place
root-qualified assignments under `spec.overrides`; see the [Overlay manifest
reference](overlay.md).

## Local tool source

`standard:local-tools` is implicitly merged into infra for every run. It
provides `tools_dir: tools` and `skills_dir: skills`, relative to the app root.
Override either path with another `ToolServerRegistry` entry using
`protocol: local`. A consumed MCP `usage: use` dependency replaces the implicit
local provider. Add an explicit local `tools` claim to keep both.

```yaml
apiVersion: infra/v1
kind: ToolServerRegistry
metadata:
  name: local-tools
spec:
  tool_servers:
    - id: local
      protocol: local
      tools_dir: tools
      skills_dir: skills
```

## ToolServerRegistry

**Where** a remote tool process lives. Not the tool's advertise contract
([tool.md](tool.md)); the agent manifest does not declare tool providers.

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
      protocol: mcp
      usage: use
      transport: streamable-http
      url: http://127.0.0.1:9001/mcp
      timeout: 30
      follow_pagination: true
      cache_scope: private
      # headers:
      #   Authorization: "env:MCP_AUTH_HEADER"
```

Canonical sample: [`library-samples/infra/mcp-localhost.yaml`](../../library-samples/infra/mcp-localhost.yaml)
(only required connection fields; runtime defaults supply optional policy).

| Field | Default | Meaning |
| ------- | --------- | --------- |
| `id` | required | Stable infra key for the remote tool server |
| `protocol` | required | `mcp` for MCP servers |
| `usage` | `use` | `use`, `deploy`, or `use-and-deploy` |
| `transport` | `streamable-http` | `stdio` \| `streamable-http` \| `sse` \| `http` |
| `url` / `endpoint` | — | HTTP/SSE URL (manifest). Optional override `env:VAR\|default` |
| `host` / `port` | `127.0.0.1:9001` | Listener address for `usage: deploy` |
| `tools_dir` | `tools` | Tool manifests served when deploying locally |
| `command` / `args` / `env` / `cwd` | — | stdio process |
| `headers` | `{}` | Omit unless auth is needed. Secrets: `env:VAR` (unset omits the header) |
| `timeout` | `30` | Per-call timeout (seconds) |
| `follow_pagination` | `true` | Walk MCP `nextCursor` and flatten |
| `cache_ttl_ms` | omit | Client list-cache TTL in ms (`0` disables; omit caches until invalidate) |
| `cache_scope` | omit | `public` \| `private` (private keys the list cache by user) |
| `tools` | `"*"` | Discover all names, or declare an explicit list in infra |

`--infra-ref` loads this document into `ResolvedInfra.tool_server_registry`.
`usage: use` connects to a remote endpoint; `usage: deploy` starts the local
server; `use-and-deploy` does both. The runtime discovers names advertised by
MCP unless `tools` is set.

For explicit local in-process bindings, see [`library-samples/infra/tool-providers.yaml`](../../library-samples/infra/tool-providers.yaml).

---

## See also

- [LLM cache](llm-cache.md) — `llm_cache` middleware guide
- [LLM cache reference](../references/llm-cache.md) — parameters, pipeline model, implementation
- [ToolServerRegistry reference](../references/tool-server-registry.md)
- [Flavour manifest](flavour.md)
- [user-config.md](../user-config.md) — workspace and `infra_refs`
- Source: `ctl/src/mas/ctl/infra/models.py`
