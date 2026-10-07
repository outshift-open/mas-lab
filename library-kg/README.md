# mas-library-kg

Trace-to-KG **normalization** and **verification** for MAS multi-agent systems.

Takes native `events.jsonl` or OTel spans and produces a Knowledge Graph
document (`kg.jsonld`) representing agent execution as an ontology-conformant graph.

**Self-contained.** No dependencies on `mas.lab.*`, `mas.ctl.*`, or `mas.runtime.*`.
Neo4j integration is an optional extra (`[neo4j]`). Ontology TTL files and KG
models come from PyPI `oxp-ontology`. OTel→KG dispatch is `norm.normalize()`
(optional extra; git stopgap until `oxp-norm` is published — the PyPI name
`norm` is already taken).

---

## Conceptual architecture

The canonical input to this library is **`events.jsonl`** — a structured trace
of agent execution events. The primary data flow:

```
events.jsonl  ←  validate against events.schema.json
    │
    │  Graph extraction
    │  normalize_events() + extract_graph()
    │  Maps each event kind to node/edge types from the MAS ontology.
    │  Resolves parent-child call chains, timestamps, and State content.
    ▼
kg.jsonld  ←  verify structural invariants + SHACL + attribute conformance
    │
    │  (optional) KG annotation
    │  annotate_kg_nodes(node_type, edge_name, value_fn)
    ▼
kg.jsonld  with additional annotation nodes + edges
```

### OTel → KG convenience path

### OTel → KG (via `norm`)

OTel spans are **not** reconstructed into events.jsonl in this library. The
public `normalize()` entry point detects OTel input and delegates to
`norm.normalize()` (see `observability/otel_via_norm.py`). Native
`events.jsonl` still uses `build_kg_document`.

```
OTel spans (ClickHouse rows or SDK JSON)
    │
    │  otel_via_norm.normalize_otel()
    │  reshape SDK → ClickHouse keys, then norm.normalize()
    ▼
(nodes, edges)  targeting oxp_ontology.models.*
```

> **Inverse direction** (`events.jsonl → OTel`) is not a concern of this
> library. That transform lives in `library-telemetry`.

### Two OTel wire formats (for the OTel path)

| Format | Key signals | Source |
|--------|------------|--------|
| **ClickHouse export** | `SpanName` / `SpanAttributes` top-level keys | Collector / ClickHouse `otel_traces` |
| **MAS SDK** (`ioa_observe`) | `name` / `attributes` / `context` top-level keys | Python `ioa_observe` / MAS SDK |

SDK spans are reshaped mechanically onto the ClickHouse keys `norm` expects.
There is no local OTel handler/dispatch in this library.

**Ontology split.** Core classes (Session, MASCall, AgentCall, LLMCall,
ToolCall, ProcessingCall, State, Transition, MAS, Agent, LLM, Tool,
Processing) come from PyPI `oxp-ontology`. Native-path classes not yet
upstream (RAGQuery, MemoryCall, SkillCall, governance, trajectory
annotations) are declared in `ontology/extensions/` pending upstream.

---

## Install

```bash
# Minimum — normalization, KG query, compare, spec, annotation
uv pip install -e library-kg

# With Neo4j push / dump support
uv pip install -e "library-kg[neo4j]"

# Development (includes pytest)
uv pip install -e "library-kg[neo4j,dev]"
```

If `oxp-ontology` is not already installed, UV resolves it from PyPI
(`oxp-ontology>=1.0.0`). The OTel path additionally needs `norm`:

```bash
uv pip install -e "library-kg[norm]"
# temporary git+subdirectory extra until oxp-norm is published
```

To validate against an unpublished local ontology version (for example `1.1.1`)
without creating a separate virtual environment, use UV's source override:

```bash
uv run --with-editable /abs/path/to/oxp-ontology pytest tests/test_validate_kg.py -q
```

This forces `oxp-ontology` to be loaded from local sources for that command.

Peer library for OTel span contracts and SpanSpec definitions:

```bash
uv pip install -e library-telemetry
```

> **Ontology TTL files** (`mas-ontology.ttl`, `mas-shapes.ttl`) are loaded from
> `oxp-ontology` so KG validation always follows the canonical ontology package.

---

## Quick start

### End-to-end: OTel spans → KG

```python
import json
from pathlib import Path
from mas.library.kg.pipeline import build_kg_from_otel_spans, write_kg_json

spans = json.loads(Path("run.otel.json").read_text())
doc = build_kg_from_otel_spans(spans, run_id="my-session-001")
write_kg_json(doc, "kg.jsonld")
```

### Two-step (access the intermediate events)

```python
from mas.library.kg.pipeline import build_kg_document, write_kg_json
from mas.library.kg.observability.normalizer import convert_spans_to_events

# Stage 1 — OTel spans → events
events = convert_spans_to_events(spans, run_id="my-session-001")

# optionally: write events.jsonl for debugging or caching
Path("events.jsonl").write_text("\n".join(json.dumps(e) for e in events))

# Stage 2 — events → KG
doc = build_kg_document(events, run_id="my-session-001")
write_kg_json(doc, "kg.jsonld")
```

### From a pre-existing events.jsonl file

```python
from mas.library.kg.pipeline import build_kg_from_events_path, write_kg_json

doc = build_kg_from_events_path("events.jsonl", run_id="my-session-001")
write_kg_json(doc, "kg.jsonld")
```

### Validate a KG

```python
from mas.library.kg.core.verifier import (
    check_containment_chain,
    check_temporal_enclosure,
    check_unknown_node_types,
    run_shacl_validation,
)

nodes = doc["nodes"]
edges = doc["edges"]

check_containment_chain(nodes, edges)       # every call node has a parent
check_temporal_enclosure(nodes, edges)      # parent fully encloses child timestamps
check_unknown_node_types(nodes)             # all node_types are ontology-declared

# SHACL — canonical conformance path, requires oxp-ontology or explicit ontology_path
run_shacl_validation(nodes, edges, ontology_path="/path/to/mas-ontology.ttl", run_id="demo")
```

### Validate events.jsonl

```python
from mas.library.kg.observability.native.validate import EventValidator

validator = EventValidator()
violations = validator.validate_file("events.jsonl", strictness="recommended")
errors = [v for v in violations if v.severity == "error"]
```

### Query and filter a KG in memory

```python
from mas.library.kg import KGIndex, FacetQuery, KGSource, KGView
import json

doc = json.loads(open("kg.jsonld").read())

# Fast typed accessors
idx = KGIndex.from_doc(doc)
print(idx.session)           # Session node or None
print(len(idx.agent_calls))  # all AgentCall nodes
print(idx.calls_by_time[:3]) # top-3 earliest calls

# Filter to a specific agent / time range
fq = FacetQuery(agent_ids=["planner"], time_range=(1700000000.0, 1700000100.0))
subgraph = KGSource(doc).apply(fq)  # dangling edges removed automatically

# Predicate search across node fields
view = KGView(doc)
llm_calls = view.select("LLMCall", model=lambda m: "gpt" in str(m).lower())
```

### Compare two KG documents

```python
from mas.library.kg import compare_kg

result = compare_kg(candidate_doc, reference_doc)
print(result.passed)    # True / False
print(result.summary)   # {"total_checks": 7, "passed": 6, "failed": 1}
for check in result.checks:
    status = "✓" if check["passed"] else "✗"
    print(f"  {status} {check['name']}: {check.get('message', '')}")
```

### Inject an app spec into a KG

```python
from mas.library.kg import build_spec_nodes, merge_spec_into_kg

spec = {
    "version": "1.0",
    "intent": "Resolve customer support tickets autonomously",
    "agents": [{"id": "triage", "role": "Classify and route tickets"}],
    "tools":  [{"id": "search_kb", "description": "Search knowledge base"}],
}

# Adds IntentSpec / AgentSpec / ToolSpec nodes + conformance edges
doc = merge_spec_into_kg(doc, spec)
```

### Push a KG to Neo4j

```python
from mas.library.kg.neo4j import push_kg_to_neo4j, denormalize

# Propagate session-scoped fields to every node/edge
doc = denormalize(doc, session_id="sess-001", app_name="my-app", source="mas-lab")
push_kg_to_neo4j(doc, uri="bolt://localhost:7687", username="neo4j", password="pw")
```

### Annotate KG nodes (optional enrichment)

`annotate_kg_nodes` is a generic utility for adding computed annotations to
nodes of any type. You provide the node type to target, the edge name to add,
and a `value_fn` that takes a node dict and returns either a dict of annotation
fields or `None` to skip:

```python
from mas.library.kg import annotate_kg_nodes
import openai

client = openai.OpenAI()

def embed_fn(node):
    content = node.get("content", "").strip()
    if not content:
        return None
    resp = client.embeddings.create(model="text-embedding-3-small", input=[content])
    return {
        "vector": resp.data[0].embedding,
        "model": "text-embedding-3-small",
        "dimensions": 1536,
    }

enriched_doc = annotate_kg_nodes(
    doc,
    node_type="State",
    edge_name="hasEmbedding",
    value_fn=embed_fn,
    annotation_node_type="StateEmbedding",
)
```

The function is pure — it returns a new document dict and does not mutate the
input. `value_fn` supplies the external computation (embedding, scoring,
classification, etc.); the library only manages graph structure.

---

## CLI

There is no standalone `mas-kg` console script — `library-kg`'s CLI is a
`kg` sub-command group registered into the shared `mas-lab` CLI (see
`lab_cli.py`'s `KgCliComponent`):

```bash
# events.jsonl → kg.jsonld
mas-lab kg normalize events.jsonl --run-id my-session --output kg.jsonld

# Validate a KG document
mas-lab kg validate kg.jsonld [--ontology-path /path/to/mas-ontology.ttl] [--strict]

# Verify an events.jsonl file
mas-lab kg verify events.jsonl [--strictness recommended]

# OTel spans → events.jsonl (preprocess only)
mas-lab kg otel-to-events otel_spans.json --run-id my-session --output events.jsonl

# Full OTel → KG in one shot
mas-lab kg otel-to-kg otel_spans.json --run-id my-session --output kg.jsonld
```

---

## Pipeline steps

`library-kg` ships standalone step functions in `mas.library.kg.steps`.
These are pure Python — no dependency on `mas.lab.benchmark.pipeline`.
`mas-lab-graph` wraps them in `PipelineStep` adapters for use in bench pipelines.

| Module | Step function | Description |
|--------|--------------|-------------|
| `steps.normalize` | `run_normalize(events_path, run_id, output_dir, *, ontology_path)` → `KGArtifact` | events.jsonl → KGArtifact |
| `steps.validate_kg` | `run_validate_kg(artifact: KGArtifact\|str\|Path, *, ontology_path, strict, fail_on_error)` → `dict` | KG structural + SHACL validation |
| `steps.verify_events` | `run_verify_events(events_path, *, strictness, fail_on_error)` → `dict` | events.jsonl validation |
| `steps.normalize_otel` | `run_normalize_otel(spans_path, run_id, output_dir, *, strict)` → `KGArtifact` | OTel → events.jsonl → KGArtifact |
| `steps.annotate` | `run_annotate(artifact: KGArtifact\|str\|Path, value_fn, *, node_type, edge_name)` → `KGArtifact` | Generic KG annotation |
| `steps.compare_kg` | `run_compare_kg(candidate: KGArtifact\|str\|Path, reference: KGArtifact\|str\|Path, *, strict)` → `dict` | Structural comparison of two KGs |
| `steps.neo4j_push` | `run_neo4j_push(artifact: KGArtifact\|str\|Path, *, uri, username, password, …)` → `dict` | Push KGArtifact to Neo4j |
| `steps.neo4j_dump` | `run_neo4j_dump(*, session_id, run_id, output_path, uri, username, password, database)` → `KGArtifact` | Fetch KG from Neo4j → KGArtifact |

Pipeline YAML definitions: [`pipelines/`](pipelines/)

---

## API reference

### Top-level (`mas.library.kg`)

Importable directly from the package:

```python
from mas.library.kg import (
    KGIndex, FacetQuery, KGSource, KGView,      # query / filter
    compare_kg, KGCompareResult,                 # comparison
    build_spec_nodes, merge_spec_into_kg,        # spec injection
    annotate_kg_nodes,                           # annotation
)
from mas.library.kg.artifact import KGArtifact, stream_artifacts  # step I/O
```

#### `KGArtifact`

The primary data type exchanged between step functions.  Holds a KG as nodes,
edges, and metadata.  Located at `mas.library.kg.artifact`.

| Member | Type | Description |
|--------|------|-------------|
| `KGArtifact.from_file(path)` | classmethod | Load from a `kg.jsonld` file |
| `KGArtifact.from_doc(doc)` | classmethod | Build from a `{"nodes": [...], "edges": [...], "metadata": {...}}` dict |
| `KGArtifact.empty()` | classmethod | Return an empty artifact |
| `.nodes` | `list[dict]` | All KG node dicts |
| `.edges` | `list[dict]` | All KG edge dicts |
| `.metadata` | `dict` | Free-form metadata (`run_id`, `created_at`, etc.) |
| `.node_count` | `int` | Number of nodes |
| `.edge_count` | `int` | Number of edges |
| `.run_id()` | method | Return `metadata["run_id"]` or `None` |
| `.session_id()` | method | Return the session ID from the `Session` node, or `None` |
| `.to_doc()` | method | Serialise to a plain `{"nodes", "edges", "metadata"}` dict |
| `.to_json()` | method | Serialise to a JSON string |
| `.save(path)` | method | Write to `kg.jsonld`; creates parent dirs; returns `Path` |
| `.push_to_neo4j(*, uri, username, password, …)` | method | Push to Neo4j; delegates to `push_kg_to_neo4j` |

#### `stream_artifacts`

```python
stream_artifacts(paths: Iterable[str | Path]) -> Iterator[KGArtifact]
```

Lazily load many `kg.jsonld` files without holding all of them in memory.  Each
file is loaded only when iterated.

```python
from mas.library.kg.artifact import stream_artifacts

for art in stream_artifacts(Path("data").glob("*/kg.jsonld")):
    print(art.run_id(), art.node_count)
```

#### `KGIndex`

Lightweight in-memory graph index with O(1) typed accessors.

| Member | Type | Description |
|--------|------|-------------|
| `KGIndex.from_doc(doc)` | classmethod | Build from a `{"nodes": [...], "edges": [...]}` dict |
| `.session` | `dict \| None` | The single `Session` node |
| `.agent_calls` | `list[dict]` | All `AgentCall` nodes |
| `.llm_calls` | `list[dict]` | All `LLMCall` nodes |
| `.tool_calls` | `list[dict]` | All `ToolCall` nodes |
| `.calls_by_time` | `list[dict]` | All call nodes sorted by `timestamp_start` |
| `.nodes` | `list[dict]` | All nodes |
| `.edges` | `list[dict]` | All edges |

#### `FacetQuery`

JSON-serializable filter spec. All fields are optional.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str \| None` | Filter to a specific session |
| `run_id` | `str \| None` | Filter to a specific run |
| `agent_ids` | `list[str] \| None` | Keep only nodes/edges for these agents |
| `call_types` | `list[str] \| None` | Keep only these call node types (e.g. `["LLMCall"]`) |
| `node_types` | `list[str] \| None` | Keep only these node types |
| `edge_types` | `list[str] \| None` | Keep only these edge types |
| `time_range` | `tuple[float, float] \| None` | Keep calls within `(start_epoch, end_epoch)` |

`FacetQuery.from_dict(d)` accepts both camelCase and snake_case keys.

#### `KGSource`

Applies a `FacetQuery` to a `kg.jsonld` dict.

```python
subgraph = KGSource(doc).apply(fq)
# → {"nodes": [...], "edges": [...]} with dangling edges removed
```

#### `KGView`

Predicate-based node search across a KG document.

```python
view = KGView(doc)
nodes = view.select("LLMCall", model=lambda m: "gpt" in str(m))
nodes = view.select("AgentCall", agentId="planner")
```

`select(node_type, **predicates)` — each kwarg is matched as equality or by calling
a callable predicate against the field value.

#### `compare_kg`

```python
result: KGCompareResult = compare_kg(candidate_doc, reference_doc, *, strict=False)
```

Runs 7 structural checks: `agent_coverage`, `node_distribution`, `edge_distribution`,
`call_depth`, `tool_coverage`, `delegation_topology`, `element_level_diff`.

`strict=True` counts element-level diff failures as failures.

#### `KGCompareResult`

| Member | Type | Description |
|--------|------|-------------|
| `.passed` | `bool` | True iff all checks passed |
| `.checks` | `list[dict]` | Per-check result dicts (`name`, `passed`, `message`) |
| `.summary` | `dict` | `{"total_checks": int, "passed": int, "failed": int}` |
| `.to_dict()` | method | Full serialisable report dict |

#### `build_spec_nodes`

```python
nodes, edges = build_spec_nodes(mas_spec)
```

Builds `IntentSpec`, `AgentSpec`, `ToolSpec`, `SkillSpec` nodes from an app spec dict.
Stable deterministic IDs (`spec:agent:<id>`, etc.) — the sub-graph is shared across
runs and can be embedded once. Each node carries `_text` for semantic embedding.

`mas_spec` optional keys: `version`, `intent` / `goal`, `agents`, `tools`, `skills`.

#### `merge_spec_into_kg`

```python
kg_doc = merge_spec_into_kg(kg_doc, mas_spec)
```

Calls `build_spec_nodes`, interns the result into `kg_doc` (no duplication), then
adds conformance edges:

- `AgentCall` / `LLMCall` → `AgentSpec` via `instanceOf`
- `ToolCall` → `ToolSpec` via `invokes`

Sets `kg_doc["meta"]["spec_injected"] = True`.

### `mas.library.kg.neo4j`

Requires `[neo4j]` extra: `uv pip install "mas-library-kg[neo4j]"`.

| Symbol | Description |
|--------|-------------|
| `push_kg_to_neo4j(doc, *, uri, username, password, database, batch_size, clear_session, ensure_indexes)` | Push a KG document to Neo4j using UNWIND-batched Cypher |
| `push_annotations_to_neo4j(doc, *, uri, username, password, database, …)` | Push annotation KGs where node refs may point to pre-existing nodes (skips `denormalize`) |
| `execute_merge(nodes, edges, driver, *, database, batch_size)` | Push pre-parsed node/edge lists to an already-open driver |
| `fetch_kg_from_neo4j(*, session_id, run_id, uri, username, password, database)` | Fetch a session KG back from Neo4j → `{"nodes", "edges"}` dict |
| `denormalize(doc, *, session_id, app_name, source, block, annotations)` | Propagate session-scoped attributes to every node/edge before push |
| `build_merge_statements(nodes, edges)` | Return dry-run Cypher string (no driver needed) |
| `KGNODE_LABEL` | `"KGNode"` — secondary label on every Neo4j node for cross-label indexing |

**`denormalize` field precedence:** caller-supplied `annotations` are applied first;
`session_id`, `app_name`, and `source` always win and cannot be overwritten by annotations.

**Edge key format:** all functions accept both `from_id`/`to_id` (canonical) and
`source`/`target` (legacy). Edges missing both are silently skipped.

### `mas.library.kg.pipeline`

| Function | Description |
|----------|-------------|
| `build_kg_from_otel_spans(spans, run_id, *, ontology_path=None, strict=True)` | End-to-end: OTel spans → KG document dict |
| `build_kg_document(events, run_id, *, ontology_path=None)` | Stage 2 only: events list → KG document dict |
| `build_kg_from_events_path(path, run_id, *, ontology_path=None)` | Load events.jsonl from disk → KG document dict |
| `write_kg_json(doc, path)` | Write KG document to `kg.jsonld`, returns `Path` |
| `load_events_jsonl(path)` | Load and parse events.jsonl into a list of dicts |
| `stream_events_jsonl(path)` | Lazy iterator over events.jsonl lines |

### `mas.library.kg.observability.normalizer` — Stage 1

| Symbol | Description |
|--------|-------------|
| `convert_spans_to_events(spans, run_id, *, strict=True, synthesize_llm_gaps=True)` | Auto-detect OTel format → events list |
| `_detect_format(spans)` | Returns `"openclaw"`, `"ioa_observe"`, or `"mas_sdk_legacy"` |

Deprecated shims (forward to the unified function):
`convert_otel_to_events`, `convert_observe_spans_to_events`

### `mas.library.kg.core.graph_builder` — Stage 2

| Symbol | Description |
|--------|-------------|
| `normalize_events(events, run_id, ontology_path=None)` | events → `(nodes, edges)` tuple |
| `extract_graph(events, run_id, *, ontology_index=None)` | Lower-level: events → `(nodes, edges)` with pre-loaded ontology |
| `extract_plot_events(raw_events)` | Filter to plottable kinds for visualization |

### `mas.library.kg.core.verifier`

| Function | Invariant |
|----------|-----------|
| `check_containment_chain(nodes, edges)` | Every non-root call node has an inbound `contains` or `hasCall` edge |
| `check_state_nesting(nodes, edges)` | AgentCall/LLMCall with content have `hasInitialState` + `hasFinalState` |
| `check_processing_call_gate(nodes, edges)` | AgentCall with LLMCall children must have a ProcessingCall child |
| `check_temporal_enclosure(nodes, edges)` | Parent timestamps fully enclose child timestamps |
| `check_unknown_node_types(nodes)` | All `node_type` values are ontology-declared |
| `check_unknown_edge_types(edges)` | All `edge_type` values are ontology-declared |
| `check_block_vocabulary(nodes)` | `block` uses `structural\|execution\|trajectory` per node_type |
| `check_layer_vocabulary(nodes)` | `layer` only on State/Transition nodes, value `"normalized"` |
| `run_shacl_validation(doc, ontology_path)` | Full SHACL shape validation (requires rdflib + pyshacl) |

### `mas.library.kg.observability.native.validate`

| Symbol | Description |
|--------|-------------|
| `EventValidator` | Validates events.jsonl against `events.schema.json` + `events.spec.yaml` |
| `EventValidator.validate_file(path, strictness)` | Returns list of `EventViolation` dataclasses |
| `StrictnessMode` | `"required"` / `"recommended"` / `"complete"` |
| `EventViolation` | Fields: `level, severity, rule, message, kind, line, field` |

### `mas.library.kg.core.annotate`

| Symbol | Description |
|--------|-------------|
| `annotate_kg_nodes(doc, *, node_type, edge_name, value_fn, annotation_node_type)` | Generic KG annotation — adds computed annotation nodes + edges |

Also importable as `from mas.library.kg import annotate_kg_nodes`.

`mas.library.kg.embeddings` is a backward-compat shim that re-exports `annotate_kg_nodes`
and the deprecated `embed_state_nodes` / `iter_state_nodes` helpers.

`annotate_kg_nodes` parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `doc` | `dict` | KG document (`{"nodes": [...], "edges": [...], ...}`) |
| `node_type` | `str` | Filter — only annotate nodes where `node["node_type"] == node_type` |
| `edge_name` | `str` | Edge type to add from source node → annotation node |
| `value_fn` | `Callable[[dict], dict \| None]` | Called with each matching node; return a dict of annotation fields, or `None` to skip |
| `annotation_node_type` | `str` | `node_type` for the new annotation nodes (default: `"Annotation"`) |

### `mas.library.kg.exceptions`

```
KGNormalizationError           (base)
├── OtelFormatError             unknown/ambiguous wire format
├── OtelSchemaError             span missing required field
├── UnknownSpanNameError        OpenClaw SpanName not in mappings
├── UnknownSpanBoundaryError    mas.boundary value not in mappings
└── MissingRequiredAttributeError  required span attribute absent
```

---

## Module layout

```
mas/library/kg/
├── __init__.py               top-level public API + package_root()
├── artifact.py               KGArtifact dataclass + stream_artifacts()
├── exceptions.py             typed exception hierarchy
├── ontology.py               TTL path resolution (oxp-ontology auto-resolve)
├── pipeline.py               public batch API — start here
│
├── core/                     pure-Python KG algorithms (no external deps)
│   ├── annotate.py           annotate_kg_nodes — generic node annotation
│   ├── query.py              KGIndex, FacetQuery, KGSource, KGView
│   ├── compare.py            compare_kg, KGCompareResult (7 structural checks)
│   ├── spec.py               build_spec_nodes, merge_spec_into_kg
│   └── verifier.py           structural + SHACL + attribute conformance checks
│
├── neo4j/                    Neo4j integration (requires [neo4j] extra)
│   ├── __init__.py           re-exports full public API
│   ├── push.py               push_kg_to_neo4j, push_annotations_to_neo4j,
│   │                         execute_merge, build_merge_statements, KGNODE_LABEL
│   ├── dump.py               fetch_kg_from_neo4j
│   └── denormalize.py        denormalize()
│
├── steps/                    standalone step functions — accept KGArtifact | str | Path
│   ├── normalize.py          run_normalize — events.jsonl → KGArtifact
│   ├── validate_kg.py        run_validate_kg — KG structural + SHACL validation → dict
│   ├── verify_events.py      run_verify_events — events.jsonl validation → dict
│   ├── normalize_otel.py     run_normalize_otel — OTel → KGArtifact via norm
│   ├── annotate.py           run_annotate — generic KG annotation → KGArtifact
│   ├── compare_kg.py         run_compare_kg — structural comparison of two KGs → dict
│   ├── neo4j_push.py         run_neo4j_push — push KGArtifact to Neo4j → dict
│   └── neo4j_dump.py         run_neo4j_dump — fetch KG from Neo4j → KGArtifact
│
├── embeddings/               backward-compat shim — re-exports core/annotate
│   └── annotate.py           annotate_kg_nodes (shim → core.annotate); embed_state_nodes (deprecated)
│
├── observability/            native extractors + thin OTel wrapper
│   ├── otel_via_norm.py      OTel SDK/ClickHouse reshape + norm.normalize()
│   ├── vocabulary.py         attribute key constants (IoaObserveAttrs, GenAIAttrs, …)
│   ├── extractors.py         pure parsing functions (normalize_attrs, stable_id, …)
│   ├── helpers.py            shared loaders, trace-cache paths
│   └── native/               native events.jsonl completeness / validate / verify
│       ├── completeness.py   check_native_trace_completeness
│       ├── validate.py       EventValidator, JSON schema validation
│       └── verify.py         native events verification helpers
│
└── schemas/
    ├── events.schema.json    JSON Schema for events.jsonl (Stage 1 output)
    └── events.spec.yaml      per-kind field spec for EventValidator
```

---

## Schemas

### `events.jsonl` — intermediate format

Each line is a JSON object. Core fields:

| Field | Type | Description |
|-------|------|-------------|
| `kind` | string | `agent_call`, `llm_call`, `tool_call`, `routing_call`, `governance_event`, … |
| `timestamp` | float | Unix epoch seconds (span start) |
| `run_id` | string | Execution run identifier |
| `call_id` | string | Stable URN for this event (derived from span ID + run) |
| `parent_call_id` | string? | Parent event's `call_id` — forms the call tree |
| `agent_id` | string? | Agent executing this span |
| `trace_id` | string | OTel trace ID |
| `span_id` | string | OTel span ID |
| `duration_ms` | float? | Span duration in milliseconds |
| `model` | string? | LLM model name (`llm_call` only) |
| `prompt_tokens` | int? | Input token count |
| `completion_tokens` | int? | Output token count |
| `input` / `output` | string? | Agent/tool I/O content |
| `synthetic` | bool? | `true` if synthesized by LLM gap-fill logic |

Full schema: [`schemas/events.schema.json`](schemas/events.schema.json)
Per-kind field spec: [`schemas/events.spec.yaml`](schemas/events.spec.yaml)

### `kg.jsonld` — Knowledge Graph document

```json
{
  "nodes": [
    {
      "id": "urn:mas:session:...",
      "node_type": "Session",
      "run_id": "...",
      "timestamp_start": 1700000000.0,
      "timestamp_end": 1700000010.0
    }
  ],
  "edges": [
    {
      "from_id": "urn:mas:session:...",
      "to_id": "urn:mas:agent:...",
      "edge_type": "hasCall"
    }
  ],
  "metadata": { "run_id": "...", "created_at": "..." }
}
```

Node types (declared in MAS ontology): `Session`, `AgentCall`, `LLMCall`,
`ToolCall`, `RoutingCall`, `GovernanceEvent`, `ProcessingCall`, `WorkerCall`,
`CallAnnotation`, `ContextContribution`, `State`, `Transition`.

Edge types: `hasCall`, `contains`, `hasInitialState`, `hasFinalState`,
`hasTransition`, `hasEmbedding`, `routedTo`, `governedBy`.

---

## Ontology sources

| TTL file | Source |
|----------|--------|
| `mas-ontology.ttl` | PyPI `oxp-ontology` |
| `mas-shapes.ttl` / `mas-shapes-custom.ttl` | PyPI `oxp-ontology` |
| Native-path extensions (RAGQuery, MemoryCall, SkillCall, governance, …) | `library-kg/ontology/extensions/` pending upstream |

Pass `ontology_path` explicitly to override the package-provided path.
Native graph extraction never requires the TTL (KIND_TO_CLASS is the map);
TTL enrichment and SHACL validation do.

---

## Relationship to other packages

| Package | Role |
|---------|------|
| `library-telemetry` (`mas.library.telemetry`) | OTel JSON schema, SpanSpec definitions, span verification and comparison. **Standalone OSS module.** The inverse (native events → OTel) direction. |
| `library-kg` (`mas.library.kg`) | Normalization + KG extraction + KG verification. **Standalone OSS module.** No internal deps. |
| `oxp-ontology` | Canonical TTL files for MAS ontology and SHACL validation. Required by `library-kg`. |
| `mas-lab-graph` | Thin pipeline step wrappers that call `library-kg` stages from `mas-bench` pipelines. |

---

## Extending

### New native event kind

1. Add the kind → class mapping in `core/event_mappings.py:KIND_TO_CLASS`.
2. If the class is not yet in PyPI `oxp-ontology`, add it to
   `ontology/extensions/mas-kg-native-extensions.ttl` and document the gap.
3. Add a native events.jsonl fixture test.

### New OTel span shape

OTel dispatch lives in `norm` (`norm.ioa_observe`). Do not add handlers in
this library. `observability/otel_via_norm.py` only reshapes SDK JSON onto
ClickHouse keys and calls `norm.normalize()`.

---

### New node type in Stage 2

1. Add `kind` → class in `core/event_mappings.py:KIND_TO_CLASS`.
2. Implement extraction in `core/graph_builder.py` if the node needs custom fields.
3. If the class is missing from oxp-ontology, add it to
   `ontology/extensions/mas-kg-native-extensions.ttl`.

---

## Development

```bash
# Install with all extras
uv pip install -e "library-kg[neo4j,dev]" -e library-telemetry

# Run tests
cd library-kg && pytest tests/

# Smoke test against a real trace
python -c "
from mas.library.kg.pipeline import build_kg_from_otel_spans
import json, pathlib
spans = json.loads(pathlib.Path('tests/fixtures/sample.otel.json').read_text())
doc = build_kg_from_otel_spans(spans, run_id='smoke-test')
print(f\"{len(doc['nodes'])} nodes, {len(doc['edges'])} edges\")
"
```

### Design principles

**Zero internal deps.** `library-kg` must not import from `mas.lab.*`,
`mas.ctl.*`, or `mas.runtime.*`. All imports are stdlib, PyPI, or within
`mas.library.kg.*`. This is what makes it shippable as a standalone OSS module.

**Single ontology source of truth.** TTL files are resolved from
`oxp-ontology` to avoid duplicated local copies.
Stage 1 and Stage 2 normalization never touch the TTL.

**Never hardcode API keys.** `state_embeddings` takes a caller-supplied
`embed_fn: Callable`. Tests mock it — never instantiate an OpenAI client inside
the library.

**Backward-compat shims preserved.** Old entry points (`convert_otel_to_events`,
`convert_observe_spans_to_events`, `IоaObserveHandler` Cyrillic alias) forward to
the unified implementations.

## Pipelines

Reusable benchmark pipeline YAMLs: [pipelines/README.md](pipelines/README.md).
Compare workflow: [docs/compare-kg.md](docs/compare-kg.md).
