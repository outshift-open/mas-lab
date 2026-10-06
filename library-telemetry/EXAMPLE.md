# A worked example: from a native trace to a verified, collector-bound span set

This walkthrough follows one multi-agent run — a **travel planner** — all the way
from its native `events.jsonl` to OTel spans that a collector (and OXP) can
ingest. Every step is shown twice: as a friendly **`mas-lab` command** (a
shortcut) and as the **pipeline** it actually runs. Reference docs are linked
inline so you can dive into any topic.

> Sample input: [`examples/travel-planner.events.jsonl`](examples/travel-planner.events.jsonl)
> — a 14-event trace where a `moderator` routes to an `itinerary_agent` and a
> `budget_agent`.

The journey:

```
events.jsonl ──①convert──▶ otel_sdk_spans.jsonl ──②verify──▶ ✓ ──③serialize──▶ OTel collector ──④dump──▶ spans back
```

Everything except the collector round-trip (③④, which needs Docker) is exercised
as a [golden test](tests/test_example_story.py), so the commands and outputs
below are real.

---

## Setup

```bash
uv pip install -e "library-telemetry[convert,verify]"   # conversion + verification
# for ③/④ you also want the collector infra and, for read-back, [clickhouse]
```

See the [install matrix](README.md#install) — every dependency is an optional
extra, so you only pull in what a step needs.

---

## ① Convert — native events → OTel spans

The `moderator`/`itinerary`/`budget` trace becomes an OTel span tree.

**Shortcut**

```bash
mas-lab telemetry convert examples/travel-planner.events.jsonl -o traces/otel_sdk_spans.jsonl
```

**What it produced** (14 events → 9 spans):

```
LLMCall × 1   ToolCall × 1   AgentCall × 3   TaskCall × 1
CallAnnotation × 2                     ← the two routing hand-offs
travel-planner.graph × 1               ← the multi-agent topology span
```

Two things the converter does that matter for OXP:

- The **application name is taken from the trace** (`app_name: travel-planner` on
  the run), not a hardcoded `mas-runtime`. Pass `--app-name` to override.
- It emits a **`<app>.graph` span** carrying the agent topology on
  `gen_ai.ioa.graph` (nodes: `orchestrator, moderator, itinerary_agent,
  budget_agent`). Without it OXP can't render the graph — see
  [docs/conversion.md § the `.graph` span](docs/conversion.md).

**The pipeline behind the shortcut** — [`pipelines/native-to-otel-json.yaml`](pipelines/native-to-otel-json.yaml):

```yaml
run:
  post:
    - ref: telemetry:native-to-otel-json
```

Its steps: `events_to_otel` (→ `steps.run_convert`) then `verify_otel`
(→ `steps.run_verify_spans`). The mapping from each event kind to a span lives
in split-by-category modules and is extensible — [docs/conversion.md § extending](docs/conversion.md).

---

## ② Verify — does the span set satisfy the contract?

**Shortcut**

```bash
mas-lab telemetry verify traces/otel_sdk_spans.jsonl --level L3
```

**Output**

```
Spans  : 9  |  traces: 1  |  agents: budget_agent, itinerary_agent, moderator, orchestrator
Conformance:
  L1: failing        # OTel GenAI semconv (not our target here)
  L2: full           # OXP — required for the UI
  L3: passing        # MAS Framework taxonomy
  L4: passing
No structural errors.
```

Verification runs three layers — structural checks, the JSON-schema envelope, and
the SpanSpec L1–L4 — see [docs/verification.md](docs/verification.md) and
[docs/spanspec.md](docs/spanspec.md). Two rules are now **mandatory**: every span
carries `application_id`, and every trace must contain a `<app>.graph` span
(drop it and `verify` fails at L2). The contract lives in
[`schemas/`](schemas/README.md).

---

## ③ Serialize — push to an OTel collector

*Where* spans go is declared by an **infra manifest** that this library owns —
the `OtelCollector` target ([`infra/local-otel.yaml`](infra/local-otel.yaml)):

```yaml
kind: Infra
spec:
  targets:
    - kind: OtelCollector
      endpoint: http://localhost:4318
```

Bring the collector up (Docker) and push:

```bash
# start a local collector; this injects $OTEL_EXPORTER_OTLP_ENDPOINT
mas-lab services start --service otel-collector --infra local-test

mas-lab telemetry push traces/otel_sdk_spans.jsonl --infra infra/local-otel.yaml
```

**Dry run** (no collector needed — builds the OTLP batches and stops):

```bash
mas-lab telemetry push traces/otel_sdk_spans.jsonl --infra infra/local-otel.yaml --dry-run
# {"spans": 9, "batches": 1, "status": "dry-run", "detail": "9 spans → http://localhost:4318/v1/traces"}
```

Endpoint precedence is `--endpoint` → manifest → `$OTEL_EXPORTER_OTLP_ENDPOINT`.
The push uses only the standard library — details in
[docs/otlp-collector.md](docs/otlp-collector.md). This is the telemetry analogue
of how `library-kg` serializes a graph to Neo4j.

**The pipeline** — [`pipelines/export-otel-collector.yaml`](pipelines/export-otel-collector.yaml)
(the `export_otel` step → `steps.run_push_otlp`), typically chained after convert:

```yaml
run:
  post:
    - ref: telemetry:native-to-otel-json
    - ref: telemetry:export-otel-collector
```

---

## ④ Dump — read the spans back

Collectors persist to ClickHouse; fetch a session back out (needs the
`clickhouse` extra and a reachable ClickHouse):

```bash
mas-lab telemetry list-apps                                   # what's in the store
mas-lab telemetry dump trip-042 -o traces/roundtrip.otel.jsonl
```

Then close the loop — confirm the round-trip preserved semantics
([docs/compare-spans.md](docs/compare-spans.md)):

```bash
mas-lab telemetry compare traces/otel_sdk_spans.jsonl traces/roundtrip.otel.jsonl
# {"passed": 6, "failed": 0, "total_checks": 6}
```

---

## The whole thing as one benchmark pipeline

```bash
mas-lab benchmark run experiment.yaml \
  --pipeline run:telemetry:native-to-kg-via-otel
```

[`native-to-kg-via-otel.yaml`](pipelines/native-to-kg-via-otel.yaml) replays the
events to OTel, verifies them, then folds them back into a KG (via `library-kg`)
and compares that to the natively-built KG — a full round-trip parity check.
Catalog: [pipelines/README.md](pipelines/README.md).

---

## Where to go next

| Topic | Doc |
|-------|-----|
| Native → OTel conversion, extending the mapping | [docs/conversion.md](docs/conversion.md) |
| SpanSpec L1–L4 conformance | [docs/spanspec.md](docs/spanspec.md) |
| Structural + schema + SpanSpec verification | [docs/verification.md](docs/verification.md) |
| Serializing to an OTLP collector / ClickHouse read-back | [docs/otlp-collector.md](docs/otlp-collector.md) |
| Span parity comparison | [docs/compare-spans.md](docs/compare-spans.md) |
| Pipeline catalog | [pipelines/README.md](pipelines/README.md) |
| API reference | [README.md](README.md) |
