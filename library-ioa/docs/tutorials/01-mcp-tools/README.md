# Tutorial 01 — MCP tools for MAS agents

This tutorial keeps the agent manifest stable and moves the remote transport
configuration into infra. The tool contract is still the same: the agent calls a
logical tool by name and arguments. What changes is only how the runtime reaches
that tool.

`library-samples/infra/mcp-localhost.yaml` declares an MCP server to consume.
The agent manifest and its tool/skill overlays contain no provider wiring.
Infra refs are dependencies: MCP `usage: use` replaces the implicit local
provider; a second local infra claim explicitly restores local tools. Flavours
control deployment/exposure, not consumed dependencies.

---

## 1. Keep the agent spec stable

The agent should not carry `spec.providers[]` for a remote MCP service. That
connection policy belongs in infra, just like A2A endpoints live in an
`Application` infra manifest.

The MCP model is:

- logical tool contract: `kind: Tool` + `call_tool(name, arguments)`
- `local` is materialized by default and uses implicit `tools/` and `skills/`
  locations from `standard:local-tools` (`protocol: local`)
- remote tool endpoint: infra `ToolServerRegistry` with `protocol: mcp`

The Tutorial 1 overlays remain unchanged. `overlays/tools.yaml` adds the
existing tool contracts, while `overlays/skills.yaml` adds the existing skill:

```yaml
# docs/tutorials/01-building-an-agent/overlays/tools.yaml
apiVersion: mas/v1
kind: Overlay
metadata:
  name: tools
spec:
  target:
    kind: Agent
  patch:
    context:
      tool_usage: |
        When you need to perform calculations, use the calc tool.
        When you need current information from the web, use the web-search tool.
    tools:
      $op:
        add:
          - ref: samples:tools/web-search.tool.yaml
          - ref: samples:tools/calc.tool.yaml
```

The implicit local entry has no `tools` claim. To retain local tools when MCP
is also configured, add this local infra dependency; id-based merge keeps the
implicit directory paths and adds the claim:

```yaml
# library-samples/infra/local-tools.yaml
apiVersion: infra/v1
kind: ToolServerRegistry
metadata:
  name: local-tools
spec:
  tool_servers:
    - id: local
      protocol: local
      tools: "*"
```

```yaml
# docs/tutorials/01-building-an-agent/overlays/skills.yaml
apiVersion: mas/v1
kind: Overlay
metadata:
  name: skills
spec:
  target:
    kind: Agent
  patch:
    skills:
      $op:
        add:
          - answer-formatting
```

The only new file needed to switch web-search to MCP is the infra manifest:

```yaml
# library-samples/infra/mcp-localhost.yaml
apiVersion: infra/v1
kind: ToolServerRegistry
metadata:
  name: mcp-localhost
spec:
  tool_servers:
    - id: localhost-mcp-tools
      protocol: mcp
      usage: use
      url: http://127.0.0.1:9001/mcp
```

This is the use dependency that makes the runtime consume web-search over MCP.
The local resource manifest is also loaded implicitly; no ref is needed for the
conventional directories:

```yaml
# library-standard/.../libs/standard/local-tools.yaml
apiVersion: infra/v1
kind: ToolServerRegistry
metadata:
  name: local-tools
spec:
  tool_servers:
    - id: local
      protocol: local
      tools_dir: tools
      skills_dir: skills
```

`protocol` and `id` are required. `usage: use` means the runtime consumes the
endpoint. `url` identifies the HTTP endpoint;
`transport` defaults to `streamable-http`. Leave `tools` unset to discover names
from MCP `tools/list`, or set it in infra to an explicit list. `usage: use` is
the consumer default. For a server, use a separate `usage: deploy` entry; its `host`,
`port`, `tools_dir`, and optional `tools` list configure what `mas-mcp serve`
exposes.

```yaml
# library-samples/infra/mcp-localhost-deploy.yaml
apiVersion: infra/v1
kind: ToolServerRegistry
metadata:
  name: mcp-localhost-deploy
spec:
  tool_servers:
    - id: mcp-localhost-deploy
      protocol: mcp
      usage: deploy
      transport: streamable-http
      host: 127.0.0.1
      port: 9001
      tools_dir: ../tools
      tools: [web-search]
```

The agent and overlay schemas do not accept `providers[]` or infra connection
fields on the agent. There is no MCP provider overlay.

The runtime reads the `ToolServerRegistry` from infra and initializes its MCP
provider from that server entry. No MCP connection fields are added to the
agent or overlays.

---

## 2. Local vs remote tool hosting

The architecture is intentionally split:

- local tools use the implicit `protocol: local` infra entry by default
- an MCP `usage: use` dependency replaces that implicit local provider
- an explicit local infra claim reselects local alongside MCP
- Flavour affects how tools are exposed, not which third-party endpoints are consumed

---

## 3. Dependencies (no vendored SDK clones)

`library-ioa` depends on the PyPI package `mcp`. Do not commit vendored SDK
checkouts.

```bash
# from mas-lab root
uv sync
# SDK CLI (`mcp version`, `mcp dev`) via extra:
uv sync --extra cli   # or install library-ioa[all]
```

Official protocol conformance is Node, not a Python clone. For the reproducible
MAS Lab fixture, install dependencies and run both pinned requirement sets with
the [MCP compliance workflow](../../../../compliance/README.md):

```bash
task --dir compliance install
task --dir compliance validate-config
MCP_CONFORMANCE_RESULTS="$PWD/compliance/results" \
  task --dir compliance run
```

---

## 4. Start the tool as a localhost MCP server

From the mas-lab repo root (terminal 1), expose one existing Tool manifest
without an infra manifest:

```bash
mas-mcp serve \
  --tool-manifest library-samples/tools/web-search.tool.yaml \
  --transport streamable-http \
  --host 127.0.0.1 --port 9001
```

Or let infra own deployment settings and discover manifests from `tools_dir`:

```bash
mas-mcp serve \
  --infra-ref library-samples/infra/mcp-localhost-deploy.yaml
```

This starts the remote MCP server; the MAS runtime does not need a patch to the
agent manifest to connect to it.

---

## 5. Run the existing agent through MCP

MCP-only replaces the default local provider. `calc` is therefore not exposed:

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  --infra-ref ../../../library-samples/infra/mcp-localhost.yaml \
  -q "What is the current price of Apple stock?" \
  --trace
```

To keep local `calc` and local skill tools, add the explicit local infra claim:

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/tools.yaml \
  -o docs/tutorials/01-building-an-agent/overlays/skills.yaml \
  --infra-ref ../../../library-samples/infra/mcp-localhost.yaml \
  --infra-ref ../../../library-samples/infra/local-tools.yaml \
  -q "What is the current price of Apple stock?" \
  --trace
```

The relative infra path is resolved from the agent manifest's directory.

There is no MCP provider overlay: consumed MCP and local tools are infra
dependencies. Agent/overlay schemas reject `providers[]`; flavours govern
exposure.

---

## 6. Why this matters

- tool manifests describe the logical interface; invocation is still `call_tool(name, arguments)`
- endpoint policy, protocol, headers, and transit details live in infra
- the agent spec stays portable and implementation-agnostic
- the same app can switch between implicit local tools and an MCP dependency by changing infra refs
- `protocol: mcp` is explicit in the infra manifest, matching the A2A pattern for protocol-aware infra declarations

---

## References

- [../../../README.md](../../../README.md)
- [../../../plugins/mcp/docs/quickstart/README.md](../../../plugins/mcp/docs/quickstart/README.md)
- [../../../plugins/mcp/docs/reference/README.md](../../../plugins/mcp/docs/reference/README.md)
- [ToolContract](../../../../docs/references/tool-contract.md)
- [kind: Tool](../../../../docs/manifests/tool.md)
- [ToolServerRegistry](../../../../docs/references/tool-server-registry.md)
- Tutorial 1 qa-agent: [../../../../docs/tutorials/01-building-an-agent/README.md](../../../../docs/tutorials/01-building-an-agent/README.md)
