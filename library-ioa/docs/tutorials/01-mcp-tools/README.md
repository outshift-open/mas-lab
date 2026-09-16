# Tutorial 01 — MCP tools for MAS agents

This is the MCP tutorial. It reuses Tutorial 1's `qa-agent` and tools overlay.
The agent-facing contract is the `web-search` name, arguments, and return
shape. The provider is `mas-mcp`, claimed through
`library-samples/overlays/mcp-localhost.yaml`.

MCP overlay/infra YAML lives in `library-samples`, not in
`docs/tutorials/01-building-an-agent/`.

---

## 1. Local provider vs MCP provider

In Tutorial 1 the tool runs in-process. Here the same logical tool is an MCP server; the runtime connects through a provider.

- the agent calls a tool by name and arguments
- **generic tool-name routing**: the runtime is a name → provider registry. Spec `providers[].kind` binds to a library plugin (`local` in library-standard, `mcp` in library-ioa). `*` providers register, then advertise names at startup; explicit lists can be checked at verification
- local is the default plugin: with no external providers, it owns `spec.tools`
- as soon as an external plugin (here MCP) is present, that implicit overlay is off. Unclaimed names raise an error. Reintroduce leftovers with `kind: local` (`library-samples/overlays/local-in-process.yaml`)

```yaml
providers:
  - name: localhost-mcp-tools
    kind: mcp
    transport: streamable-http
    url: http://127.0.0.1:9001/mcp
    tools: "*"          # discovery query: own every name this server advertises
  - name: in-process
    kind: local
    tools: "*"          # remaining spec.tools (e.g. calc) stay local
  # - name: search-only
  #   kind: mcp
  #   url: http://127.0.0.1:9001/mcp
  #   tools: [web-search]   # explicit: only this name
```

`tools: "*"` means: register the provider, then at runtime init send a discovery query (`tools/list` on MCP) and **update the registry with the advertised set**. Verification always passes for `*`. Explicit lists skip that query, beat `*`, and can be checked at verification. Two `*` plugins advertising the same name is an error — pin the name on one of them.

---

## 2. Dependencies (no vendored SDK clones)

`library-ioa` depends on the PyPI package `mcp`. Do not commit `mcp-python-sdk` or `mcp-conformance` checkouts.

```bash
# from mas-lab root
uv sync
# SDK CLI (`mcp version`, `mcp dev`) via extra:
uv sync --extra cli   # or install library-ioa[all]
```

Official protocol conformance is Node, not a Python clone:

```bash
npx @modelcontextprotocol/conformance server --url http://127.0.0.1:9001/mcp
```

---

## 3. Start the tool as a localhost MCP server

From the mas-lab repo root (terminal 1):

```bash
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --host 127.0.0.1 \
  --port 9001 \
  --transport streamable-http
```

HTTP serve defaults to `--json-response --stateless-http` (Inspector and `mas-mcp tools` need that). Stdio is also valid:

```bash
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --tool web-search \
  --transport stdio
```

The server logs `MCP tool call name=web-search arguments=...` on each invocation.

---

## 4. Prove the server with the MCP client CLI

Same repo, another terminal — this is the SDK-backed client (`mas-mcp tools`), not curl JSON-RPC:

```bash
mcp version

mas-mcp tools list --url http://127.0.0.1:9001/mcp

mas-mcp tools call --url http://127.0.0.1:9001/mcp \
  --tool web-search \
  --arguments '{"query":"Apple stock price"}'
```

Expect `web-search` in the list, a non-error payload from `call`, and a matching `MCP tool call` line on the server terminal.

---

## 5. Run Tutorial 1's qa-agent through MCP

Canonical overlay/infra live in samples (not the tutorial tree):

- `library-samples/overlays/mcp-localhost.yaml` — plugin `kind` + name claim (`tools: "*"`). Sets `url` on `providers[]`; overlay keys win over infra.
- `library-samples/overlays/local-in-process.yaml` — leftover `spec.tools` stay local
- `library-samples/infra/mcp-localhost.yaml` — WHERE: transport, timeout `30`, `follow_pagination: true`, `cache_scope: private`. No env vars required. Secrets, if needed, use `env:VAR`.

```bash
# terminal 2 — qa-agent from Tutorial 1, MCP overlay from samples
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o library-samples/overlays/mcp-localhost.yaml \
  -o library-samples/overlays/local-in-process.yaml \
  --infra-ref library-samples/infra/mcp-localhost.yaml \
  -q "What is the current price of Apple stock?" \
  --trace --trace-summary
```

`--trace --trace-summary` (not `-v` on `chat`). You should see `AGENT → TOOL[web-search]` and a new `MCP tool call name=web-search` line on the **server** process.

Validate the overlay on this branch:

```bash
mas-ctl validate docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o library-samples/overlays/mcp-localhost.yaml \
  -o library-samples/overlays/local-in-process.yaml
```

---

## 6. Why this matters

- tool manifests describe the logical interface; invocation is `call_tool(name, arguments)`
- optional advertise fields (title, hints, `output_schema`) live on `kind: Tool`
- provider overlays decide which plugin claims which names
- infra `ToolServerRegistry` decides where that plugin connects
- the same qa-agent YAML runs in-process (Tutorial 1) or over MCP (this tutorial)
- MCP overlay/infra YAML lives in `library-samples`; Tutorial 1's tree is the in-process qa-agent

---

## References

- [../../../README.md](../../../README.md)
- [../../../plugins/mcp/docs/quickstart/README.md](../../../plugins/mcp/docs/quickstart/README.md)
- [../../../plugins/mcp/docs/reference/README.md](../../../plugins/mcp/docs/reference/README.md)
- [ToolContract](../../../../docs/references/tool-contract.md)
- [kind: Tool](../../../../docs/manifests/tool.md)
- [ToolServerRegistry](../../../../docs/references/tool-server-registry.md)
- Tutorial 1 qa-agent: [../../../../docs/tutorials/01-building-an-agent/README.md](../../../../docs/tutorials/01-building-an-agent/README.md)
