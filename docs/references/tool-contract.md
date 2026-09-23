<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# ToolContract

**Module:** `mas.runtime.contracts.tool_contract`

`ToolContract` is the runtime boundary for **listing** and **calling** tools.
The engine, local plugin, and MCP plugin all dispatch through
`call_tool(tool_name, arguments)`.

```python
provider.call_tool("web-search", {"query": "Apple stock price"})
```

1. The LLM (or test) emits a tool name plus a JSON object of arguments.
2. The runtime registry looks up the name and forwards to the owning plugin.
3. Local tools: `ToolContract.call_tool` validates arguments and calls `execute(**arguments)`.
4. MCP: `MCPToolProvider.call_tool` sends MCP `tools/call` with the same name and arguments.

`execute(**kwargs)` is the in-process helper for a **single** tool class.
Composite providers (local registry, MCP, skill tools) override `call_tool`
and do not go through `execute`.

MCP `tools/call` **is** this method. Extra MCP SDK parameters and result
parts are optional kwargs / optional envelope keys on the same call, or they
are connection policy on infra — they are not a second invocation API.

---

## Required surface

| Method | Required payload |
|--------|------------------|
| `list_tools()` | `[{name, description, parameters}]` |
| `call_tool(tool_name, arguments)` | dict / envelope with `result` (and `is_error` on failure) |
| `execute(**kwargs)` | local single-tool helper only |

`invoke_call_tool` forwards optional kwargs only when the callee declares them
(or takes `**kwargs`).

---

## Optional advertise (`list_tools` / `kind: Tool`)

Emitted only when set. Schema: [`tool.schema.yaml`](../schemas/runtime/tool.schema.yaml).
Guide: [tool.md](../manifests/tool.md).

| Contract getter / YAML | `list_tools` key |
|------------------------|------------------|
| `get_title()` / `spec.title` | `title` |
| `get_output_schema()` / `spec.output_schema` | `output_schema` |
| `is_idempotent()` / `spec.idempotent` | `idempotent` |
| `is_read_only()` / `spec.read_only` | `read_only` (`None` = omit) |
| `is_destructive()` / `spec.destructive` | `destructive` |
| `is_open_world()` / `spec.open_world` | `open_world` |
| `get_icons()` / `spec.icons` | `icons` |
| `get_task_support()` / `spec.task_support` | `task_support` |
| `get_meta()` / `spec.meta` | `meta` |
| `get_semantics()` / `spec.semantics` | `semantics` |
| `get_timeout_seconds()` / `spec.timeout_seconds` | `timeout_seconds` |

---

## Optional `call_tool` kwargs

```python
call_tool(
    tool_name,
    arguments,
    timeout_seconds=None,
    progress_callback=None,
    cancel_event=None,          # accepted; no MCP SDK mapping
    meta=None,
    input_responses=None,
    request_state=None,
    allow_input_required=None,
    allow_claimed=None,
    ctx=None,
    user="",
)
```

The default `ToolContract.call_tool` ignores these and runs
`execute(**arguments)`. The MCP client forwards the ones the SDK supports
(`read_timeout_seconds`, `progress_callback`, `meta`, elicitation flags).

---

## Optional result keys (`ToolResultEnvelope`)

Daily payload is `{status, result, is_error}` (plus `result_mode` /
`execution_mode` on the envelope). Extra keys appear only when set:
`content`, `structured_content`, `result_type`, `meta`.

---

## Not on ToolContract — infra `ToolServerRegistry`

These describe **where** the server lives, not **what** the tool is, and not
how it is invoked:

| Field | Place |
|-------|--------|
| `url` / `endpoint`, `transport`, `command` / `args` / `env` / `cwd` | Infra tool server |
| HTTP `headers` (secrets: `env:VAR`; omit when unused) | Infra tool server |
| Connection `timeout` | Infra tool server (also allowed on `providers[]`) |
| `follow_pagination` (flatten `nextCursor`; default `true`) | Infra tool server |
| `cache_ttl_ms` / `cache_scope` (list-result cache policy) | Infra tool server |

A contract-only caller uses `list_tools()` and `call_tool(name, arguments)`.
It does not see URL, headers, pagination, or cache policy.

Reference: [infra.md — ToolServerRegistry](../manifests/infra.md#toolserverregistry) ·
[tool-server-registry.md](tool-server-registry.md).
Example: [`library-samples/infra/mcp-localhost.yaml`](../../library-samples/infra/mcp-localhost.yaml).

Agent `spec.providers[]` names the plugin (`kind`) and the claim
(`tools: "*"` or an explicit list). Overlay `providers[]` may also set
`url`; when both overlay and infra set a key, the overlay value is used.

---

## See also

- [tool.md](../manifests/tool.md)
- [agent.md](../manifests/agent.md)
- [tool-server-registry.md](tool-server-registry.md)
- MCP mapping: `library_ioa.plugins.mcp.contract`
