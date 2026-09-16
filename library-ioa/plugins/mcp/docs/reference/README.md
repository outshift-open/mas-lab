# MCP reference

Plugin types (library-ioa, not runtime):

- `library_ioa.plugins.mcp.spec.MCPProviderSpec` — maps `spec.providers[]` onto client config
- `library_ioa.plugins.mcp.contract` — MCP `Tool` / `CallToolResult` ↔ MAS `list_tools` / `call_tool`
- `library_ioa.plugins.mcp.client.MCPClient` — stdio / streamable-HTTP / SSE session
- `library_ioa.plugins.mcp.provider.MCPToolProvider` — `kind: mcp` tool-provider plugin
- `library_ioa.plugins.mcp.server.MCPToolServerFactory` — wrap a MAS `Tool` YAML as an MCP server
- CLI: `mas-mcp serve`, `mas-mcp tools list`, `mas-mcp tools call`

`call_tool(name, arguments)` is the required invocation. Optional kwargs and
advertise fields: [ToolContract](../../../../docs/references/tool-contract.md).

## Manifests

| Document | Owns |
|----------|------|
| `kind: Tool` | Advertise: name, parameters, optional title/hints/output_schema. [tool.md](../../../../docs/manifests/tool.md) |
| Overlay `spec.providers[]` | Plugin `kind` + name claim (`tools: "*"` or a list) |
| `infra/v1` `ToolServerRegistry` | Where: url, transport, headers, timeout, pagination. [reference](../../../../docs/references/tool-server-registry.md) |

Examples:

- [`library-samples/overlays/mcp-localhost.yaml`](../../../../library-samples/overlays/mcp-localhost.yaml)
- [`library-samples/infra/mcp-localhost.yaml`](../../../../library-samples/infra/mcp-localhost.yaml)
- [`docs/schemas/examples/tools/annotated.tool.yaml`](../../../../docs/schemas/examples/tools/annotated.tool.yaml)

## Optional keys

A tool that implements `call_tool(self, name, arguments)` and `list_tools()`
returning `{name, description, parameters}` is complete. `invoke_call_tool`
forwards optional kwargs only when the callee declares them. Tool YAML may
omit advertise extras. Overlay `providers[]` may set `url`; when both overlay
and infra set a key, the overlay value is used.
