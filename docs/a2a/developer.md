# A2A developer reference

## Contract boundaries

`DelegationContract` owns the LLM-visible `delegate_to_<agent>` tool surface.
`AgentCommContract` owns only the low-level send operation after delegation has
already been decided. Its implementations are selected by the runtime registry:

- `LocalAgentComm`: in-process bus.
- `A2AAgentComm`: official `a2a-sdk` client.

The A2A server is a separate ingress adapter. It maps incoming A2A
`message/send` calls to `ControlContract.send_message` (queue a turn at
the tail via the session mailbox) and is not an `AgentCommContract`
implementation. `AgentCommContract.send` is outbound peer send after
delegation.

A2A has no steer RPC. Additional messages on a non-terminal working task
are queued; they do not preempt an in-flight decode. Control-protocol
`steer` can preempt (keep the prefix, replace the rest), replace
(discard the prefix, new turn), or wait (`after`: queue to front until
the current generation finishes). `tasks/cancel` maps to
`cancel_inflight` (drop the remainder; success is not guaranteed).
`input-required` is HITL, not a mid-token splice.

## Registry and routing

The public protocol configuration lives in `infra/v1` `Application.spec.endpoints`,
keyed by the exact agency agent id. The runtime registry category remains
`agent_comm`; the endpoint's `protocol` selects its implementation. The MAS-wide
in-process comm variant is resolved from `spec.agent_comm` (`protocol` or
`type`) via `registry.create`, not chosen by the delegation plugin or hardcoded
in `ctl`. The route builder resolves every `delegates_to` target against
materialized local agency entries and infra endpoints. Missing targets fail
during wiring.

## AgentCard

`agent_card_from_manifest()` maps manifest metadata and skills to the official
A2A `AgentCard`. It always emits at least one skill, capabilities, default input
and output modes, provider organization, and JSON-RPC/REST interfaces.

## Task lifecycle

MAS already has `session_id` for a complete run and `task_id` for each input
operation. A2A `contextId` and `taskId` are mapped to those values at ingress;
`messageId` identifies the submitted message. Parent and correlation identifiers
are sent in A2A message metadata. This avoids creating a second session model.

The current executor supports immediate text responses and cancellation. Full
artifact production, `INPUT_REQUIRED` continuation, durable task storage, and
multi-replica subscription require additional adapters and are tracked in the
A2A compliance page rather than silently claimed as complete.

## Exposure topology

The infra endpoint entry is both the outbound reachability declaration and the
place to mark public availability with `expose: true` or `usage: deploy`. They
are intentionally independent of agency topology: a private local worker may be
exposed, an external dependency may be consumed without being exposed, and an
agent may have both a local `ref` and a named infra endpoint when an overlay
deliberately routes it remotely.

`mas-ctl serve`, `chat`, `tui`, and `run-mas` share one exposure helper
(`mas.ctl.session.exposure`). Listen URLs come from Application endpoints:

- dedicated `serve`: blocking listener for that agent (`usage: deploy` or
  `use-and-deploy` required).
- `chat` / `tui`: the in-process agent is the conversation owner; a deployed
  endpoint binds in the background for interrogation while stdin/curses stay
  the conversation.
- `run-mas`: the entry agent is always in-process. A deployed entry endpoint
  binds for interrogation. Hosted specialists with `usage: deploy` (not
  `use`) get their own ports. `usage: use` / `use-and-deploy` peers are
  client routes; another `mas-ctl serve` owns those ports.

`--bind NAME=a2a://…` is a shortcut for an Application `usage: use` row: it
expands to `--override infra:spec.endpoints…` on the same merged infra
document as `--infra-ref`. It is not a second exposure path.

A single port cannot safely host multiple independent AgentCards without a
routing convention and stable URL paths; that is not inferred.

## Compliance workflow

The optional tooling lives under `compliance/`. The official A2A TCK is kept as
a Git checkout because its top-level runner is not included in the published
wheel. The official `a2a` CLI is a Go binary. MCP uses the official npm
conformance framework. Reports are generated outside runtime tests and should
be attached to the feature validation record.
