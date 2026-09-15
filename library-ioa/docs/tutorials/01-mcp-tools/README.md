# Tutorial 01 — MCP tools for MAS agents

This follows Tutorial 1 and keeps the same agent-facing tool contract. The only thing that changes is the provider: the tool still has the same name, arguments, and return shape, but it is now exposed through an MCP-backed infra provider.

The important architectural point is that MAS tools are resolved through a provider registry, not hard-coded to the in-process local implementation.

---

## 1. Local provider vs MCP provider

In Tutorial 1 the tool lived locally in the same Python process. Here we expose the same logical tool through an MCP server and let the MAS runtime connect to it through a provider.

The result is the same logical API to the agent:

- the agent calls a tool by name and arguments
- the provider resolves where the tool lives
- the runtime dispatches to the selected provider

This is the foundation for infra manifests, remote tool ownership, and dynamic provider selection.

```yaml
providers:
  - name: local-tools
    kind: local
```

That is the local in-process path. The MCP path is the same call pattern, just through a server-backed provider.

---

## 2. Start the tool as a localhost MCP server

Use the MAS wrapper to expose an existing tool manifest without creating any temporary glue script:

```bash
cd .

mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --host 127.0.0.1 \
  --port 9001 \
  --transport streamable-http
```

This keeps the real tool implementation exactly as it is and exposes it as an MCP server on localhost. For a different transport, replace only the transport configuration; the rest of the pattern is the same.

```bash
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --transport stdio
```

The `stdio` case is valid, but for the infra-style workflow the localhost HTTP port is the clearer pattern.

---

## 3. Verify the server advertises the tool

```bash
curl -s http://127.0.0.1:9001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

This confirms the MCP server is advertising its tool set. In an auto-discovery flow, `tools: "*"` depends exactly on this behavior.

---

## 4. Call the tool over MCP

```bash
curl -s http://127.0.0.1:9001/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0",
    "id":2,
    "method":"tools/call",
    "params":{
      "name":"web-search",
      "arguments":{"query":"Apple stock price"}
    }
  }'
```

This is the real functional proof that the tool contract is preserved across the provider boundary.

---

## 5. Generic overlay for infra/MPL provider selection

The generic overlay is intentionally discovery-based:

```yaml
providers:
  - name: localhost-mcp-tools
    kind: mcp
    transport: streamable-http
    url: http://127.0.0.1:9001/mcp
    tools: "*"
```

The important detail is that this is not a static list of known tools. `tools: "*"` means: ask the MCP server which tools it advertises and register them at runtime.

This is why a generic overlay cannot include a static `tool_usage` block that names `web-search` in advance. The tool is known only when discovery succeeds.

The agent can still be guided by prompts or task-level policy, but the provider itself is discovery-driven.

---

## 6. Follow-up from Tutorial 1

The tutorial flow becomes:

```bash
# Terminal 1: expose the tool through MCP
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --host 127.0.0.1 \
  --port 9001 \
  --transport streamable-http
```

```bash
# Terminal 2: run the Tutorial 1 agent with the MCP-backed provider overlay
mas-ctl chat agent.yaml \
  -o overlays/tools.yaml \
  -o overlays/mcp-localhost.yaml \
  -q "What is the current price of Apple stock?" \
  -v
```

This keeps the same tutorial pattern as Tutorial 1, but the tool is served by a separate MCP process instead of being resolved locally.

---

## 7. Why this matters

This is the core Mas-Lab pattern:

- tool manifests describe the logical interface
- provider manifests decide where that interface is served from
- the runtime dispatches to the provider that matches the current deployment model
- a generic overlay can advertise `*` and discover the tool set from the upstream server

That is what makes the same agent portable between local execution and infra-managed tool services.

---

## References

- [../../../README.md](../../../README.md)
- [../../../plugins/mcp/docs/quickstart/README.md](../../../plugins/mcp/docs/quickstart/README.md)
- [../../../../docs/tutorials/01-building-an-agent/README.md](../../../../docs/tutorials/01-building-an-agent/README.md)
