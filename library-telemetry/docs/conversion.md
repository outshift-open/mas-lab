# Native events → OTel spans (conversion)

This is the core transform of `library-telemetry`, and the inverse of what
`library-kg` does:

```
library-kg:        OTel spans ──▶ events.jsonl ──▶ kg.json
library-telemetry: events.jsonl ──▶ OTel spans ──▶ (verify / OTLP collector)
```

The authoritative input is **`events.jsonl`** — a structured trace of native MAS
execution events (the same file `library-kg` normalises *from*). Each `*_start`/
`*_end` pair becomes one interval span; singleton events become point (zero-width)
spans.

```
events.jsonl
   │  replay_events_file()  /  MasOtelConverter.process_event()
   │  • dispatch each event kind to a registered handler
   │  • reconstruct the span tree from call_id / parent_call_id
   │  • preserve timestamps (float seconds → ns)
   ▼
otel_sdk_spans.jsonl   (one ReadableSpan JSON per line)
```

## Two modes

**Offline replay** (batch, from a file) — the common case:

```python
from mas.library.telemetry.conversion import replay_events_file

n = replay_events_file(
    "runs/item0/traces/events.jsonl",
    "runs/item0/traces/otel_sdk_spans.jsonl",
    service_name="mas-runtime",
    app_name="my-app",
)
```

**Live** (during agent execution) — a plugin builds a minimal event dict per hook
and calls `converter.process_event(event)`. The same handler code runs in both
modes, so replayed traces are span-for-span identical to live ones (enforced by
the parity tests).

```python
from mas.library.telemetry.conversion import MasOtelConverter, ExportLayers

converter = MasOtelConverter(tracer, app_name="my-app",
                             export_layers=ExportLayers(governance=True))
for event in events:
    converter.process_event(event)
converter.flush_open_spans()
```

## Design: thin core + category handlers (extensible mapping)

Following the same principle as `library-kg`'s OTel→KG mappings, the per-`kind`
logic is **not** a single flat dispatch table. It is split into category modules
that mirror the ontology *blocks*, and assembled through a decorator registry.

```
conversion/
├── converter.py        stateful span-tree core + primitive API (open/close/point)
├── exporter.py         JSONLineFileSpanExporter
├── replay.py           replay_events_file — offline batch entry point
├── layers.py           ExportLayers — which layers to emit
├── envelope.py         kind → (block, summand, mealy) — the categorization table
├── tool_name.py        resolve_tool_name
└── mappings/
    ├── base.py         register() decorator + SpanEmitter protocol + build_handler_table()
    ├── structural.py   mas_call (TaskCall), execution (AgentCall), infrastructure (Worker)
    ├── execution.py    llm / tool / processing / skill / network / workflow / communication
    ├── memory.py       memory_store / memory_read / memory_retrieve / rag_query
    ├── context.py      context_assembled / context_part / state_update / compaction
    ├── governance.py   governance / policy / hitl / budget / control
    └── trajectory.py   routing / user I/O / parallel_group / obs_wrap_gov
```

A **handler** is a plain function `handler(conv, event) -> None`. It never touches
converter internals — it emits spans through the `SpanEmitter` primitive API:

| Primitive | Purpose |
|-----------|---------|
| `conv.open_span(call_id, name, attrs, parent_call_id, start_ns)` | open an interval span |
| `conv.close_span(call_id, extra, status, end_ns)` | close it |
| `conv.point_span(name, attrs, parent_call_id, ts_ns, call_id)` | zero-width point span |
| `conv.ts_ns(ev)` / `conv.agent_id(ev)` / `conv.require_call_id(ev)` / `conv.enc(v)` | helpers |
| `conv.is_open(id)` / `conv.is_closed(id)` | span-state queries |
| `conv.emit_duplicate_start_annotation(ev, kind)` | dedupe repeated `*_start` |

### Extending the mapping

Adding support for a new event `kind` is two steps — nothing in `converter.py`
changes:

1. Add a row to `envelope.KIND_ENVELOPE` (`kind → (block, summand, mealy_symbol)`)
   so the event is categorised and layer-gated correctly.
2. Add a handler in the category module matching its block, decorated with
   `@register`:

```python
# conversion/mappings/execution.py
from mas.library.telemetry.conversion.mappings.base import register, SpanEmitter

@register("embedding_call_start")
def h_embedding_call_start(conv: SpanEmitter, ev):
    conv.open_span(conv.require_call_id(ev), "EmbeddingCall", {
        "mas.boundary": "EmbeddingCall",
        "mas.agent.id": conv.agent_id(ev),
        "mas.embedding.model": ev.get("model") or "unknown",
    }, ev.get("parent_call_id"), start_ns=conv.ts_ns(ev))

@register("embedding_call_end")
def h_embedding_call_end(conv: SpanEmitter, ev):
    conv.close_span(ev.get("call_id"), status=ev.get("status", "success"), end_ns=conv.ts_ns(ev))
```

Third-party code can register handlers too — just import and call `register`
before constructing a converter. One handler can serve several kinds:
`@register("policy_allow", "policy_denial")`.

Verify what is registered:

```bash
mas-lab telemetry kinds            # 53 built-in handlers, grouped by block
```

```python
from mas.library.telemetry.conversion import registered_kinds
print(len(registered_kinds()))
```

## Export layers

`ExportLayers` gates which events are emitted, keyed off each event's ontology
block (via `envelope.export_layer_for_kind`):

| Layer | Blocks | Default |
|-------|--------|---------|
| `structure` | structural | on |
| `execution` | execution | on |
| `semantic` | context | on |
| `provenance` | trajectory | on |
| `governance` | governance | off |

The OXP-required defaults are structure, execution, and trajectory
(``provenance``). Semantic stays on with that set. Governance is opt-in:

```python
replay_events_file(..., export_layers={"governance": True})
```

## Determinism

`replay_events_file` seeds a stable session uuid from `(file, service_name)`, so
repeated replays of the same events produce identical span/trace ids — which is
what makes the [span parity](compare-spans.md) checks meaningful.

## References

- Categorization: `papers/mas-ontology-kg` appendices R.2–R.3 (block / summand /
  Mealy symbol), reproduced in `conversion/envelope.py`.
- Inverse transform: `library-kg` `docs/kg-spec.md`.
