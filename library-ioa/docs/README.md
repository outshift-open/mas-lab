# IOA Library Documentation

## Introduction
Welcome to the IOA documentation. This section covers the architecture and usage of the IOA library and the MCP integration pattern used by MAS runtime providers.

## Quickstart

- [MCP Quickstart](../plugins/mcp/docs/quickstart/README.md) — start a server and connect to it with a MAS manifest

## User Guide

The MCP bridge supports both deployment patterns:

1. Direct local tool calls in-process for lightweight development
2. Separate MCP server process for remote or infra-style tool exposure

The provider contract is the same either way: the agent asks for a tool name and arguments, and the runtime resolves it through the provider registry.

## Developer Guide

The core pieces are:

- `library_ioa.plugins.mcp.client` — official SDK-backed client session wrapper
- `library_ioa.plugins.mcp.server` — server factory scaffold for exposing MAS tools over MCP
- `mas.runtime.plugins.mcp_provider_plugin.MCPProviderPlugin` — manifest registration hook
- `mas.runtime.engine.mcp_tool_provider.MCPToolProvider` — adapter between MAS tool invocation and MCP tool calls

This keeps the protocol boundary explicit while preserving the same MAS tool schema for callers.

## Tutorial follow-up

See the MCP tutorial in [tutorials/01-mcp-tools/README.md](tutorials/01-mcp-tools/README.md) for a follow-up to the first MAS agent tutorial.
