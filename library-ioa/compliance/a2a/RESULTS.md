# Compliance results

## A2A

Target: Tutorial 1 QA agent served by `mas-ctl serve --protocol a2a`.

Tools:

- official `a2a` CLI v0.3.0: card discovery and message send passed;
- official A2A TCK, JSON-RPC + HTTP+JSON, MUST level: `71.6%` on the
	LLM-backed QA endpoint;
- report: `vendor/a2a-tck/reports/compatibility.json`.

Passing areas include AgentCard discovery, declared JSON-RPC interface,
interface schema validation, task response schema, and basic message exchange.

The remaining MUST failures are `DM-ART-001` and `DM-MSG-001`. They are
deterministic fixture-response expectations from the TCK artifact scenario, not
transport or AgentCard failures. The SDK-backed executor supports structured
text artifacts when the agent handler returns them; the default QA LLM handler
does not produce an artifact for the TCK artifact prompt. Optional extensions
were skipped when not declared.

This is an honest partial conformance result, not a full A2A compliance claim.

The deterministic fixture's latest dual-transport MUST run has no MUST
failures: `54 PASS`, `38 SKIPPED`, and `22 NOT TESTED`. Skipped and untested
cases correspond to capabilities or transports not declared by the fixture.
