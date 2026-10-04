# A2A agent communication

MAS Lab supports the A2A protocol as a registered agent transport. A2A is
separate from LLM access, MCP tool/resource access, and delegation policy.

Every live-agent entry point (`mas-ctl serve`, `chat`, `tui`, `run-mas`) uses
the same `agent_expose` path (`mas.ctl.session.exposure`). Listen URLs come
from an `infra/v1` Application endpoint, not from CLI `--protocol` / `--host`
/ `--port` flags.

## Quickstart

Declare the listener in infra, keyed by the agent `metadata.name`:

```yaml
apiVersion: infra/v1
kind: Application
metadata:
  name: a2a-qa
spec:
  endpoints:
    qa-agent:
      protocol: a2a
      usage: deploy
      url: http://127.0.0.1:9005
```

Dedicated server process:

```bash
mas-ctl serve docs/tutorials/01-building-an-agent/agent.yaml \
  --infra-ref path/to/a2a-qa.yaml
```

The same bind happens in the background when that agent is the in-process
conversation owner:

```bash
mas-ctl chat docs/tutorials/01-building-an-agent/agent.yaml \
  --infra-ref path/to/a2a-qa.yaml -i
```

`--bind` is a shortcut for the same Application / ToolServerRegistry fields
(`usage: use`). It expands to `--override infra:…` and is merged with
`--infra-ref` YAML; there is no second bind resolver. Flavour stays `local`:

```bash
mas-ctl run-mas mas.yaml \
  --bind banking_assistant=a2a://127.0.0.1:8080/agents/banking_assistant/ \
  --bind analyze_transaction_risk=mcp://127.0.0.1:8080/mcp#analyze_transaction_risk
```

Inspect the card and send a message with the official A2A CLI:

```bash
a2a card get http://127.0.0.1:9005
a2a send -a http://127.0.0.1:9005 "What is the capital of France?"
```

The endpoint serves `/.well-known/agent-card.json` and advertises the JSON-RPC
and HTTP+JSON interfaces supported by the installed SDK.

## MAS configuration

`workflow.nodes[].delegates_to` declares who may be contacted. Infrastructure
declares how each named agent is reached:

```yaml
spec:
  agency:
    agents:
      - id: moderator
        ref: agents/moderator.yaml
      - id: weather-oracle
  workflow:
    entry: moderator
    nodes:
      - id: moderator
        delegates_to: [weather-oracle]
      - id: weather-oracle
```

An agency entry without `ref` is an external dependency. An entry with `ref`
and no matching infra endpoint is local and uses the local agent bus. The
matching infra endpoint is keyed by the same agent id.

## Public exposure

A public agent endpoint is an infra Application endpoint keyed by agent name:

```yaml
spec:
  endpoints:
    weather-oracle:
      protocol: a2a
      usage: deploy
      url: http://127.0.0.1:9005
```

`mas-ctl serve` hosts one agent per process (blocking). `chat`, `tui`, and
`run-mas` host the conversation in-process and bind every deployed endpoint
this process owns: the conversation agent, plus specialists with `usage:
deploy` only. Specialists with `usage: use` or `use-and-deploy` stay remote;
run a separate `mas-ctl serve` for those ports. One AgentCard per listen URL;
path-based multiplexing on a single port is not inferred.

## Task and session identity

- A2A `contextId` maps to MAS `session_id` and working-memory continuity.
- A2A `taskId` maps to one MAS input operation.
- A2A `messageId` maps to one submitted turn.
- A2A `message/send` maps to `ControlContract.send_message` (queue a turn).
- A2A `tasks/cancel` maps to `ControlContract.cancel_inflight`.
- There is no A2A steer RPC; preempt / replace / after are control-protocol only.
- MAS correlation and parent-call identifiers travel in A2A message metadata.

See [developer.md](developer.md) and the [compliance report](../../library-ioa/docs/a2a/protocol-compliance.md).
