# MCP protocol compliance

MCP and A2A are separate protocol surfaces. MCP exposes tools, resources,
prompts, sampling, roots, notifications, and transport bindings; A2A exposes
agents, messages, tasks, and task lifecycle.

## External test command

The official MCP conformance framework is installed and invoked with npm:

```bash
npx @modelcontextprotocol/conformance server \
  --url http://127.0.0.1:9001/mcp
```

Pin a released specification revision with `--requirements`, for example:

```bash
npx @modelcontextprotocol/conformance server \
  --url http://127.0.0.1:9001/mcp \
  --requirements 2026-07-28
```

## Current scope

The AGNTCON MCP scenario proves the streamable-HTTP tool path. A complete
conformance run still needs to be recorded for resources, prompts, roots,
notifications, authentication, and each supported specification revision.
Results belong under the separate `compliance/` workflow, not in runtime unit
tests.
