# MCP quickstart

This follows the same model as Tutorial 1: the logical tool contract stays the same, while the provider changes.

- local mode: the tool is resolved in-process
- MCP mode: the tool is exposed by a separate server and the runtime connects to it

## 1. Local provider mode

```yaml
providers:
  - name: local-tools
    kind: local
```

This is the direct in-process path. It is the simplest development flow.

## 2. Start the tool as an MCP server on localhost

```bash
cd .

mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --host 127.0.0.1 \
  --port 9001 \
  --transport streamable-http
```

This is the recommended infra-style deployment for a local service. The same file-wrapping pattern also works with `stdio`, but for localhost deployment the port-based flow is cleaner and easier to reason about.

## 3. Connect the runtime to the server

```yaml
providers:
  - name: localhost-mcp-tools
    kind: mcp
    transport: streamable-http
    url: http://127.0.0.1:9001/mcp
    tools: "*"
```

`tools: "*"` is the generic discovery mode. The runtime asks the MCP server which tools it advertises and registers the returned set.

## 4. Verify the tool is advertised

```bash
curl -s http://127.0.0.1:9001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

This proves the server is advertising its tool surface. That is exactly the signal the generic `*` overlay depends on.

## 5. Call the tool

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

This confirms the tool contract is preserved across the provider boundary.

## 6. Why this matters

The runtime-facing contract is stable, while the deployment model is flexible:

- same agent logic
- same tool name and arguments
- different provider backends
- local or server-backed discovery depending on environment

That is what allows the same MAS agent to run in local development mode or behind an infra-owned MCP service without redefining the tool contract.
