# A2A agent communication

MAS Lab supports the A2A protocol as a registered agent transport. A2A is
separate from LLM access, MCP tool/resource access, and delegation policy.

## Quickstart

Start a manifest-backed agent through the generic runtime server command:

```bash
mas-ctl serve docs/tutorials/01-building-an-agent/agent.yaml \
  --protocol a2a --host 127.0.0.1 --port 9005
```

Inspect its dynamically generated card and send a message with the official
A2A CLI:

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
      url: http://127.0.0.1:9005
      expose: true
```

The current `mas-ctl serve` command serves one agent manifest. A
multi-agent launcher and path-based multi-agent server are not yet enabled;
use separate ports when exposing several agents.

## Task and session identity

- A2A `contextId` maps to MAS `session_id` and working-memory continuity.
- A2A `taskId` maps to one MAS input operation.
- A2A `messageId` maps to one submitted turn.
- A2A `message/send` maps to `ControlContract.send_message` (queue a turn).
- A2A `tasks/cancel` maps to `ControlContract.cancel_inflight`.
- There is no A2A steer RPC; preempt / replace / after are control-protocol only.
- MAS correlation and parent-call identifiers travel in A2A message metadata.

See [developer.md](developer.md) and the [compliance report](../../library-ioa/docs/a2a/protocol-compliance.md).
