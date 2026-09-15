# IOA Library

The IOA (Intelligent Orchestration Agent) library provides specialized capabilities for MAS agents, starting with MCP (Model Context Protocol) support.

## Overview
This library is designed to extend the MAS ecosystem with advanced interoperability and orchestration features. The MCP bridge is implemented as a runtime plugin and a client/server adapter, so an agent can either call tools locally in-process or connect to a separate MCP server process that exposes the same tool contract.

## Contents
- **Plugins**: Extensible agent capabilities (e.g., MCP).
- **Libs**: Core logic and helper libraries.
- **Utils**: Shared utility functions.

## Quickstart

### 1. Run the tool server as an MCP server

The implementation supports a stdio MCP server that exposes a tool over the official SDK. Start it in its own process:

```bash
cd .
PYTHONPATH=../mcp-python-sdk/src python -c '
from mcp.server import MCPServer
mcp = MCPServer("math-tools")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

mcp.run("stdio")
'
```

This exposes the `add` tool over MCP using stdio, which is the same transport path used by the MAS runtime provider bridge.

### 2. Register the server in a MAS manifest

Use the `kind: mcp` provider entry to connect the runtime to the server:

```yaml
providers:
  - name: math-tools
    kind: mcp
    transport: stdio
    command: python
    args:
      - -c
      - |
        from mcp.server import MCPServer
        mcp = MCPServer("math-tools")

        @mcp.tool()
        def add(a: int, b: int) -> int:
            return a + b

        mcp.run("stdio")
```

This is the provider-level “all tools from this server” model. You can also keep a single MCP server per tool when you want tighter ownership boundaries.

### 3. Run the agent against the MCP provider

```bash
mas-ctl chat agent.yaml -q "Use the calculator and add 2 + 3" \
  -o overlays/mcp-tools.yaml
```

The same agent can also use local tools directly in-process without the MCP server if you prefer the simpler local-provider path.

## Development notes

- The bridge lives in the `library_ioa.plugins.mcp` package.
- The runtime provider plugin registers `kind: mcp` manifests through `MCPProviderPlugin`.
- The SDK-backed client connects using `mcp.client.stdio.stdio_client` and `ClientSession`.
- A separate MCP server process can therefore expose the same business tool contract without changing the agent manifest contract.

## Related docs

- [docs/README.md](docs/README.md)
- [plugins/mcp/docs/quickstart/README.md](plugins/mcp/docs/quickstart/README.md)
