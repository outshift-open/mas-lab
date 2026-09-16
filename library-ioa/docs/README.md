# IOA Library Documentation

## Introduction
Welcome to the IOA documentation. This section covers the architecture and usage of the IOA library and the MCP integration pattern used by MAS runtime providers.

## Quickstart

- [MCP Quickstart](../plugins/mcp/docs/quickstart/README.md) — start a server and connect to it with a MAS manifest

## User Guide

The MCP bridge supports both deployment patterns:

1. Direct local tool calls in-process for lightweight development
2. Separate MCP server process for remote or infra-style tool exposure

The provider contract is the same either way: the agent asks for a tool name and arguments via `call_tool(name, arguments)`. Optional advertise fields live on `kind: Tool`. Connection URL, headers, timeout, and pagination live on infra `ToolServerRegistry`.

## Developer Guide

The core pieces are:

- `library_ioa.plugins.mcp.spec` — map every `spec.providers[]` field onto the client
- `library_ioa.plugins.mcp.contract` — MCP `tools/list` / `tools/call` ↔ MAS `ToolContract`
- `library_ioa.plugins.mcp.client` — official SDK-backed client session wrapper
- `library_ioa.plugins.mcp.server` — serve a MAS `kind: Tool` manifest over MCP
- `mas.runtime.registry.tool_provider_registry` — name → provider routing; spec `kind` binds via the plugin URN registry
- `library_ioa.plugins.mcp.provider.MCPToolProvider` — MCP adapter (`kind: mcp`)

This keeps the protocol boundary explicit while preserving the same MAS tool schema for callers.

See [ToolContract](../../docs/references/tool-contract.md), [kind: Tool](../../docs/manifests/tool.md), and [ToolServerRegistry](../../docs/references/tool-server-registry.md).

## Tutorial follow-up

See the MCP tutorial in [tutorials/01-mcp-tools/README.md](tutorials/01-mcp-tools/README.md).
It reuses Tutorial 1's qa-agent without modifying that tutorial; overlays live in `library-samples`.
