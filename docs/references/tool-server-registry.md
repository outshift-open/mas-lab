<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# ToolServerRegistry (`infra/v1`)

**Kind:** `ToolServerRegistry` · **Schema:** [`infra-tool-server.schema.yaml`](../schemas/runtime/fragments/infra-tool-server.schema.yaml) · **Guide:** [infra.md](../manifests/infra.md#toolserverregistry)

This is the **WHERE** of remote tools: URL, transport, headers, timeouts, stdio
process, list pagination, list-cache policy. It is **not** the tool advertise
contract (`kind: Tool`) and **not** which names an agent claims
(`spec.providers[]`).

Invocation stays `ToolContract.call_tool(name, arguments)`. Connection policy
never belonged on that method.

---

## Split of concerns

| Document | Owns |
|----------|------|
| `kind: Tool` | What the tool is: name, parameters, optional title / hints / `output_schema`. [tool.md](../manifests/tool.md) |
| Overlay / Agent `spec.providers[]` | Which plugin (`kind`) and which names (`tools: "*"` or a list) |
| `infra/v1` `ToolServerRegistry` | Where that plugin connects |

Match overlay `providers[].name` to `tool_servers[].id`. Unset connection
fields on the provider are filled from the matching server. When both overlay
and infra set a key, the overlay value is used.

---

## Shape

```yaml
apiVersion: infra/v1
kind: ToolServerRegistry
metadata:
  name: mcp-localhost
spec:
  tool_servers:
    - id: localhost-mcp-tools          # required; match providers[].name
      name: localhost-mcp-tools        # display; defaults to id
      description: Local mas-mcp HTTP
      transport: streamable-http       # default
      url: http://127.0.0.1:9001/mcp
      timeout: 30                      # default
      follow_pagination: true          # default
      cache_scope: private
      # headers:
      #   Authorization: "env:MCP_AUTH_HEADER"
```

Canonical sample: [`library-samples/infra/mcp-localhost.yaml`](../../library-samples/infra/mcp-localhost.yaml).

Attach with `--infra-ref library-samples/infra/mcp-localhost.yaml` (or workspace
`infra_refs`). Pair with [`library-samples/overlays/mcp-localhost.yaml`](../../library-samples/overlays/mcp-localhost.yaml).

---

## Field reference

Every field except `id` is optional. Defaults below are what the sample ships
and what the MCP client uses when the key is omitted.

### Identity

| Field | Default | Notes |
|-------|---------|--------|
| `id` | required | Stable id. Overlay `providers[].name` should match. |
| `name` | `id` | Display name. Also accepted as a lookup alias. |
| `description` | omit | Human note; not sent on the wire. |

### HTTP / SSE

| Field | Default | Notes |
|-------|---------|--------|
| `transport` | `streamable-http` | `stdio` \| `streamable-http` \| `sse` \| `http` |
| `url` | — | HTTP/SSE endpoint (e.g. `http://127.0.0.1:9001/mcp`). Put the URL in the manifest. Optional override: `env:VAR\|http://127.0.0.1:9001/mcp`. |
| `endpoint` | — | Alias for `url` |
| `headers` | `{}` | HTTP headers. Omit when the server needs no auth. Secrets use `env:VAR` (unset omits the header). Never hardcode tokens. |
| `timeout` | `30` | Per-call timeout in seconds (`read_timeout_seconds` on MCP) |

### stdio process

Used when `transport` is `stdio` (or when `command` is set and `url` is not).

| Field | Default | Notes |
|-------|---------|--------|
| `command` | — | Executable |
| `args` | `[]` | Argument list |
| `env` | `{}` | Extra environment for the child. Secrets may use `env:VAR`; other values belong in the manifest. |
| `cwd` | — | Working directory |

```yaml
- id: local-stdio-mcp
  transport: stdio
  command: mas-mcp
  args: [serve, --tool-manifest, library-samples/tools/web-search.tool.yaml, --transport, stdio]
```

### List transport

| Field | Default | Notes |
|-------|---------|--------|
| `follow_pagination` | `true` | Walk MCP `tools/list` `nextCursor` pages and flatten. `false` = first page only. |
| `cache_ttl_ms` | omit | Client `tools/list` cache TTL in milliseconds. Omit = cache until `invalidate`. `0` = no cache. |
| `cache_scope` | omit | `public` (one list for all users) or `private` (list cache keyed by user). |

These are **not** ToolContract fields. A tool's advertise document does not
know how the client paginates or caches `tools/list`.

---

## Overlay vs infra

Overlay `providers[]` may set `url` / `transport` / `timeout` / `headers`.
When both overlay and infra set a key, the overlay value is used. A
`ToolServerRegistry` that only declares `id` + `url` validates
(`additionalProperties: true` on the fragment keeps leftover protocol keys).
Infra fields are not arguments to `call_tool`.

---

## What does not belong here

| Concern | Place |
|---------|--------|
| Tool name, parameters, title, hints, `output_schema` | `kind: Tool` |
| Plugin kind and name claim (`*` vs list) | `spec.providers[]` |
| Per-tool wall-clock cap advertised to the LLM | `kind: Tool` `timeout_seconds` (optional) |
| Secrets | `headers: { Authorization: env:VAR }` (omit the block when unused) or `PersonalSecrets` |
| API / URL override | `url: env:VAR\|http://127.0.0.1:9001/mcp` — manifest default, env wins when set |

---

## See also

- [infra.md](../manifests/infra.md#toolserverregistry) — kinds table and sample
- [tool.md](../manifests/tool.md) — advertise contract
- [tool-contract.md](tool-contract.md) — `call_tool`
- Schema: [`infra.schema.yaml`](../schemas/runtime/infra.schema.yaml)
