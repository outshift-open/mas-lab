# MCP quickstart

Same pattern as the [MCP tutorial](../../../docs/tutorials/01-mcp-tools/README.md): this flow reuses Tutorial 1's qa-agent; `library-samples` supplies the MCP overlay.

- local mode: the tool is resolved in-process
- MCP mode: `mas-mcp serve` exposes it; overlay `providers` with `tools: "*"` register, then discover names at runtime init

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

## 3. Overlay (from samples)

See `library-samples/overlays/mcp-localhost.yaml` (claim) and
`library-samples/infra/mcp-localhost.yaml` (connection defaults: timeout 30,
`follow_pagination: true`, `cache_scope: private`). Overlay may set `url`;
when both overlay and infra set a key, the overlay value is used. Add
`--infra-ref library-samples/infra/mcp-localhost.yaml` to load the infra
document. No env vars are required. If the server needs auth, add
`headers: { Authorization: env:VAR }` — never hardcode tokens. To override
the URL at deploy time, use `env:VAR|http://127.0.0.1:9001/mcp`.

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o library-samples/overlays/mcp-localhost.yaml \
  -o library-samples/overlays/local-in-process.yaml \
  -q "What is the current price of Apple stock?" \
  --trace
```

`tools: "*"` on MCP registers the provider, then discovers names at runtime init (`mas-ctl validate` always passes). Tutorial 1's `tools.yaml` also adds `calc`; keep it in-process with `-o library-samples/overlays/local-in-process.yaml`. Prod MCP-only deployments omit that overlay and must not declare unclaimed tools.

## 4. Dependencies

PyPI `mcp` (optional extra `library-ioa[cli]` / `[all]`). Do not vendor `mcp-python-sdk` or `mcp-conformance`. Conformance:

```bash
npx @modelcontextprotocol/conformance server --url http://127.0.0.1:9001/mcp
```
