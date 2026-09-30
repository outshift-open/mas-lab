# A2A protocol compliance

This page records external interoperability evidence for the SDK-backed A2A
server. It is not a claim that every optional A2A feature is implemented.

## Evidence

| Check | Result |
| --- | --- |
| Official `a2a` CLI card discovery | Passed against Tutorial 1 agent |
| Official `a2a` CLI message send | Passed against Tutorial 1 agent |
| Official A2A TCK, all transports and requirement levels | 79.8% on the deterministic SUT |
| Report | [`compliance/a2a/a2a-tck-compatibility-2026-09-29.json`](../../compliance/a2a/a2a-tck-compatibility-2026-09-29.json) |

## Implemented

- AgentCard discovery at `/.well-known/agent-card.json`.
- JSON-RPC and REST interfaces advertised in the card.
- Text messages and task completion through the official SDK.
- Cancellation event construction.
- Context/task/message identity mapping.
- Dynamic card fields from the manifest.

## Deterministic compliance SUT

The compliance agent uses the `scripted_response` design pattern and the
positive A2A infrastructure profile. It routes the TCK's session-suffixed
`messageId` values to exact task, artifact, streaming, and message responses
while serving gRPC, JSON-RPC, and HTTP+JSON through the production exposure
path. The full TCK result is `88/114 MUST`, `7/11 SHOULD`, and `4/4 MAY`, with
`246 passed, 19 skipped` at the pytest level and 15 transport-scoped skips in
the compatibility report.

This is the correct way to test protocol semantics reproducibly. It does not
make production LLM agents return canned output.

## Known gaps

The LLM-backed endpoint is not a deterministic TCK fixture and therefore should
not be used to score exact fixture semantics. The remaining unscored
requirements are visible in the compatibility report and must not be presented
as passes.
