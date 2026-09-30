# MCP reference

Plugin types (library-ioa, not runtime):

- `library_ioa.plugins.mcp.spec.MCPProviderSpec` — maps an infra server entry onto client config
- `library_ioa.plugins.mcp.contract` — MCP `Tool` / `CallToolResult` ↔ MAS `list_tools` / `call_tool`
- `library_ioa.plugins.mcp.client.MCPClient` — stdio / streamable-HTTP / SSE session
- `library_ioa.plugins.mcp.provider.MCPToolProvider` — `kind: mcp` tool-provider plugin
- `library_ioa.plugins.mcp.server.MCPToolServerFactory` — wrap a MAS `Tool` YAML as an MCP server
- `library_ioa.plugins.mcp.tasks.MCPTasksExtension` — production MCP Tasks/MRTR extension
- CLI: `mas-mcp serve`, `mas-mcp tools list`, `mas-mcp tools call`

`call_tool(name, arguments)` is the required invocation. Optional kwargs and
advertise fields: [ToolContract](../../../../docs/references/tool-contract.md).

`MCPToolServerFactory` also exposes `add_prompt`, `add_resource`,
`add_completion`, and `add_request_handler` for applications that register
additional MCP capabilities. The standard `mas-mcp serve` CLI remains a
tool-manifest entry point; callers that need these additional capabilities
construct the factory and register them explicitly.

## Manifests

| Document | Owns |
|----------|------|
| `kind: Tool` | Advertise: name, parameters, optional title/hints/output_schema. [tool.md](../../../../docs/manifests/tool.md) |
| `infra/v1` `ToolServerRegistry` | Protocol, tool discovery/claim, URL, transport, headers, timeout, pagination. [reference](../../../../docs/references/tool-server-registry.md) |

Examples:

- [`library-samples/infra/mcp-localhost.yaml`](../../../../library-samples/infra/mcp-localhost.yaml)
- [`docs/schemas/examples/tools/annotated.tool.yaml`](../../../../docs/schemas/examples/tools/annotated.tool.yaml)

## Optional keys

A tool that implements `call_tool(self, name, arguments)` and `list_tools()`
returning `{name, description, parameters}` is complete. `invoke_call_tool`
forwards optional kwargs only when the callee declares them. Tool YAML may
omit advertise extras. The agent spec does not carry provider connection fields.
