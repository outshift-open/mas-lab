---
name: uncertainty-protocol
description: >
  Structured gap-check and confidence-scoring protocol for analyst agents.
  Use this before writing any conclusion or hypothesis to ensure every claim
  is backed by evidence and gaps are explicitly declared rather than filled
  by speculation.
metadata:
  version: "1.0.0"
  domain: sre
  tags: [uncertainty, protocol, shared]
---

# Uncertainty Protocol — Telemetry Analyst

Before writing any conclusion or hypothesis, complete the following block exactly.
Do not skip it even if you believe the answer is obvious.

## Required Gap-Check Block

After completing all tool calls for a question, produce:

```
EVIDENCE_ACCESSED:
  - <tool_name>(<params>) → <key result in one line>
  - ... (one line per call made this turn)

GAPS:
  - <question you cannot answer from the above results>
  - ... (empty list = [] if nothing is missing)

CONFIDENCE: <0.0–1.0>
  Rule: must be ≤ 0.5 if GAPS is non-empty.
  Rule: must cite at least one EVIDENCE_ACCESSED entry to justify values > 0.7.
```

## When GAPS is non-empty

Do **not** proceed to a conclusion. Instead write:

```
CLARIFICATION_NEEDED: <the single most important missing piece>
SUGGESTED_SOURCE: <which agent or tool could provide it>
```

Do not fabricate an answer to fill the gap. A stated gap is more useful
than a confident wrong conclusion.

## Telemetry-specific scope limits

These questions are outside the telemetry agent's tool set. If asked about them,
list them in GAPS and suggest the appropriate agent:

| Question | Correct agent |
|----------|---------------|
| Root cause of DB connection pool saturation | DB Specialist |
| Whether a deployment is responsible | Backend Engineer |
| Whether a rollback is safe | Backend Engineer + Verifier |
| Business impact in revenue terms | Comms Agent |

## Reporting Format

Every conclusion must follow: **Observed → Evidence → Limitation**

```
OBSERVED:   error_rate on payment-service = 23.2% (from get_metrics)
EVIDENCE:   get_metrics("payment-service", metric="error_rate", window="15m") → 0.232
LIMITATION: cannot determine if deployment at 09:55 is causal without backend data
```
