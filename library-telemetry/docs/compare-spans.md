# Span parity comparison

Round-trip parity is how we prove the converter is faithful: replay `events.jsonl`
to spans, and check the result matches a reference (a live plugin export, or a
second replay). This mirrors `library-kg`'s `compare_kg` for the span domain.

`compare_otel_span_sets` compares **semantics**, not identifiers. Trace ids, span
ids, and timestamps are ignored (they legitimately differ between replay and live
export); span order is not significant.

## Checks (6)

| Check | Compares |
|-------|----------|
| `span_count` | total number of spans |
| `span_name_counts` | count of spans per `name` |
| `mas_attr_keys_by_name` | set of `mas.*` attribute keys per span name |
| `topology` | parent→child edges keyed by span **name** (multiset) |
| `max_depth` | maximum tree depth |
| `mas_attr_values` | multiset of `(name, mas.* values)` signatures (excl. `mas.call.id`) |

## Usage

```python
from mas.library.telemetry import compare_otel_span_sets, OtelSpanSet

ref = OtelSpanSet.from_file("otel_sdk_spans.jsonl")        # live plugin export
cand = OtelSpanSet.from_events("events.jsonl", app_name="x")  # replay

report = cand.compare_to(ref, strict=True)
print(report["passed"], report["summary"])   # {'passed': 6, 'failed': 0, 'total_checks': 6}
```

Files / step / CLI:

```python
from mas.library.telemetry.steps import run_compare_spans, run_compare_spans_multi
run_compare_spans("reference.jsonl", "candidate.jsonl", strict=True, output_path="parity.json")
run_compare_spans_multi("reference.jsonl", [("otel-plugin", "a.jsonl"), ("observe-sdk", "b.jsonl")])
```

```bash
mas-lab telemetry compare reference.jsonl candidate.jsonl --output parity.json
```

## Typical workflow

```
events.jsonl ──replay──▶ otel_sdk_spans_replay.jsonl ─┐
                                                       ├─▶ compare ─▶ parity_report.json
live plugin ───────────▶ otel_sdk_spans.jsonl ────────┘
```

See the [`otel-span-parity`](../pipelines/otel-span-parity.yaml) pipeline, which
replays a reference and compares it against both the OTel and observe plugin
live exports.
