---
name: memory-protocol
description: >
  Structured episodic memory protocol for agents operating in a multi-agent
  system. Use this to write and read findings in a canonical format that
  downstream agents can reliably retrieve. Prevents duplicate tool calls and
  cross-agent correlation failures.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [memory, protocol, shared]
---

# Memory Protocol

All agents share an episodic store. Unstructured writes cannot be reliably
retrieved downstream. Use this format for every write.

## Write format — Evidence Card

Every time you write to memory, produce exactly one card per finding:

```
MEMORY_WRITE:
  service:       <service name, e.g. payment-service>
  metric:        <what was measured, e.g. p99_latency_ms>
  value:         <observed value or range, e.g. 4200>
  timestamp:     <ISO-8601 or "from run_id=<id>">
  source_agent:  <your agent name>
  tool_call:     <tool_name(params) that produced this value>
  interpretation: <one-sentence meaning, e.g. "exceeds 2 000 ms SLO">
```

Write multiple cards if a single tool call yields multiple distinct facts.
Do not combine unrelated facts in one card.

## Read format — Structured Query

Before calling a tool that another agent may already have run, query memory:

```
MEMORY_READ:
  service: <service name>
  metric:  <metric name>
```

If the store returns a match, use it and note:

```
RECALLED: <service>/<metric> = <value> (from <source_agent>)
```

Do not re-run the same tool call if a valid recall exists.

## What not to write

- Do not write summaries or prose paragraphs to memory.
- Do not write hypotheses or confidence scores.
- Do not write tool errors (write `GAPS` in the uncertainty block instead).

## SRE-specific guidance

The SRE agent's writes should cover:
- Severity classification decisions and the evidence that triggered them
- Escalation routing decisions (which specialist was engaged and why)
- Time-to-first-response milestones
