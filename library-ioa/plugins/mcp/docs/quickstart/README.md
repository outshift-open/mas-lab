# MCP quickstart

Same pattern as the [MCP tutorial](../../../docs/tutorials/01-mcp-tools/README.md): this flow reuses Tutorial 1's qa-agent; infra supplies the MCP endpoint.

- local mode: the tool is resolved in-process
- MCP mode: `mas-mcp serve` exposes it; infra `ToolServerRegistry` declares the endpoint, and runtime discovers names

## 1. Serve

From the mas-lab repo root:

```bash
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --host 127.0.0.1 \
  --port 9001 \
  --transport streamable-http
```

## 2. MCP client CLI (not curl)

```bash
mcp version
mas-mcp tools list --url http://127.0.0.1:9001/mcp
mas-mcp tools call --url http://127.0.0.1:9001/mcp \
  --tool web-search --arguments '{"query":"Apple stock price"}'
```

The serve process logs `MCP tool call name=web-search`.

## 3. Infra (from samples)

`library-samples/infra/mcp-localhost.yaml` declares protocol `mcp` and the
endpoint. The transport and client policy use runtime defaults. No env vars are
required. If the server needs auth, add
`headers: { Authorization: env:VAR }` — never hardcode tokens. To override
the URL at deploy time, use `env:VAR|http://127.0.0.1:9001/mcp`.

To let infra configure the server listener and tools directory, use the
`usage: deploy` sample:

```bash
mas-mcp serve \
  --infra-ref library-samples/infra/mcp-localhost-deploy.yaml
```

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/skills.yaml \
  --infra-ref ../../../library-samples/infra/mcp-localhost.yaml \
  --infra-ref ../../../library-samples/infra/local-tools.yaml \
  -q "What is the current price of Apple stock?" \
  --trace
```

Runtime discovers MCP tool names at initialization. Tutorial 1's `calc` tool
remains local because the MCP server only advertises `web-search`.

## 4. Dependencies

PyPI `mcp` (optional extra `library-ioa[cli]` / `[all]`). Do not vendor `mcp-python-sdk` or `mcp-conformance`.

Run the self-contained SDK integration fixture and both pinned requirement sets.
The reproducible workflow, installation steps, and CI artifact policy live in
[`compliance/`](../../../../compliance/README.md):

```bash
task --dir compliance install
task --dir compliance validate-config
task --dir compliance run
```

All tool, prompt, resource, completion, legacy-method, and Tasks scenarios
exercise production MCP adapter APIs. The fixture supplies deterministic
handlers; it does not bypass `MCPToolServerFactory` or the production Tasks
extension. The `mas-mcp serve` CLI exposes tool manifests directly; applications
that need the additional capabilities construct the factory and register them
explicitly with `add_prompt`, `add_resource`, `add_completion`, or extensions.
