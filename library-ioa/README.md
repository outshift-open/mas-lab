# IOA Library

MCP (Model Context Protocol) client and server bridge for MAS Lab.

Agents keep the same tool names and arguments. Generic runtime routing is a
name → provider registry. Local is the default plugin. Once an
external plugin (MCP) is present, names must be claimed (`tools: "*"`
registers the provider then discovers names at runtime init, or an explicit
list) or reintroduced with `kind: local`. Unclaimed names error. Explicit
claims beat discovery. Star claims always pass `mas-ctl validate`. Two `*`
plugins advertising the same name is an error.

## Layout

- `src/library_ioa/plugins/mcp/spec.py` — `spec.providers[]` → client config
- `src/library_ioa/plugins/mcp/contract.py` — MCP Tool/CallToolResult ↔ MAS list_tools/call_tool
- `src/library_ioa/plugins/mcp/client` — SDK-backed client (one session per list/call)
- `src/library_ioa/plugins/mcp/provider.py` — `kind: mcp` tool-provider plugin
- `src/library_ioa/plugins/mcp/server` — wrap a MAS tool manifest as an MCP server (`mas-mcp`)
- `src/library_ioa/utils` — result/error helpers
- `docs/` — tutorial
- `plugins/mcp/docs/` — MCP quickstart and contract-gap reference

Reusable YAML lives in **`library-samples`**, not Tutorial 1:

- `library-samples/overlays/mcp-localhost.yaml`
- `library-samples/overlays/local-in-process.yaml`
- `library-samples/infra/mcp-localhost.yaml`

## Dependencies

```toml
dependencies = ["mcp>=2.2"]           # PyPI; not a git clone of mcp-python-sdk
optional-dependencies.cli = ["mcp[cli]"]
optional-dependencies.all = ["mcp[cli]"]
```

Protocol conformance is Node `@modelcontextprotocol/conformance` (`npx`). Do not
commit vendored `mcp-python-sdk` / `mcp-conformance` trees.

## Quickstart

From the mas-lab repo root (after `uv sync`):

```bash
# terminal 1
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --host 127.0.0.1 \
  --port 9001 \
  --transport streamable-http
```

```bash
# terminal 2 — official SDK CLI + mas-mcp client
mcp version
mas-mcp tools list --url http://127.0.0.1:9001/mcp
mas-mcp tools call --url http://127.0.0.1:9001/mcp \
  --tool web-search --arguments '{"query":"Apple stock price"}'

mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o library-samples/overlays/mcp-localhost.yaml \
  -o library-samples/overlays/local-in-process.yaml \
  -q "What is the current price of Apple stock?" \
  --trace --trace-summary
```

The serve terminal must log `MCP tool call name=web-search` for both `mas-mcp tools call` and the agent.

## Runtime wiring

- `MCPClient` opens/closes streamable-HTTP in the same asyncio task (`run_sync` from the provider)
- `LocalToolProvider` — default in-process Python `spec.tools` (`kind: local`, library-standard)
- `MCPToolProvider` — `kind: mcp` (`library_ioa.plugins.mcp.provider`)

## Related docs

- [docs/README.md](docs/README.md)
- [docs/tutorials/01-mcp-tools/README.md](docs/tutorials/01-mcp-tools/README.md)
- [plugins/mcp/docs/quickstart/README.md](plugins/mcp/docs/quickstart/README.md)
- [plugins/mcp/docs/reference/README.md](plugins/mcp/docs/reference/README.md)
- [ToolContract](../docs/references/tool-contract.md)
- [kind: Tool](../docs/manifests/tool.md)
- [ToolServerRegistry](../docs/references/tool-server-registry.md)
