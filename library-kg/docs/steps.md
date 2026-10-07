# Step functions — `mas.library.kg.steps`

This document is a complete reference and example guide for all eight step
functions shipped in `mas-library-kg`.

---

## What steps are

Step functions are standalone, pure-Python entry points that cover the
full KG lifecycle — from raw events or OTel spans through normalisation,
validation, annotation, comparison, and Neo4j persistence.

They are deliberately kept free of any dependency on `mas.lab.*`,
`mas.ctl.*`, or `mas.runtime.*`.  This means they work in any Python
context — a Jupyter notebook, a one-off script, or a CI job — without
pulling in the entire bench stack.

`mas-lab-graph` wraps each step in a thin `PipelineStep` adapter so the
same logic is available inside `mas-bench` YAML pipelines without
reimplementing anything.

### Input types

Steps that accept a KG as input take **`KGArtifact | str | Path`**:

- Pass a `KGArtifact` object directly when chaining steps in memory (no
  disk round-trip required).
- Pass a `str` or `pathlib.Path` to a `kg.jsonld` file — the step loads it
  automatically.

```python
from mas.library.kg.artifact import KGArtifact

# From disk
art = KGArtifact.from_file("runs/001/kg.jsonld")

# From a dict (e.g. built in-memory by the pipeline API)
art = KGArtifact.from_doc({"nodes": [...], "edges": [...], "metadata": {...}})
```

### Return types

| Return type | Steps |
|-------------|-------|
| `KGArtifact` | `run_normalize`, `run_normalize_otel`, `run_annotate`, `run_neo4j_dump` |
| `dict` (report) | `run_validate_kg`, `run_verify_events`, `run_compare_kg`, `run_neo4j_push` |

---

## Step overview

| Module | Function | Input (KG) | Output | One-line description |
|--------|----------|-----------|--------|----------------------|
| `steps.normalize` | `run_normalize` | `events.jsonl` path | `KGArtifact` | events.jsonl → KG |
| `steps.normalize_otel` | `run_normalize_otel` | OTel spans path | `KGArtifact` | OTel spans → events.jsonl → KG |
| `steps.validate_kg` | `run_validate_kg` | `KGArtifact \| str \| Path` | `dict` | Structural + SHACL validation |
| `steps.verify_events` | `run_verify_events` | `events.jsonl` path | `dict` | events.jsonl schema + spec validation |
| `steps.annotate` | `run_annotate` | `KGArtifact \| str \| Path` | `KGArtifact` | Generic node annotation |
| `steps.compare_kg` | `run_compare_kg` | `KGArtifact \| str \| Path` (×2) | `dict` | Structural parity comparison |
| `steps.neo4j_push` | `run_neo4j_push` | `KGArtifact \| str \| Path` | `dict` | Push KG to Neo4j |
| `steps.neo4j_dump` | `run_neo4j_dump` | — (fetches from Neo4j) | `KGArtifact` | Fetch KG from Neo4j |

All step functions are importable directly from `mas.library.kg.steps`:

```python
from mas.library.kg.steps import (
    run_normalize,
    run_normalize_otel,
    run_validate_kg,
    run_verify_events,
    run_annotate,
    run_compare_kg,
    run_neo4j_push,
    run_neo4j_dump,
)
```

---

## 1. `run_normalize` — events.jsonl → KGArtifact

**Module:** `mas.library.kg.steps.normalize`

### Signature

```python
from mas.library.kg.steps import run_normalize

def run_normalize(
    events_path: str | Path,
    run_id: str,
    output_dir: Optional[str | Path] = None,
    *,
    ontology_path: Optional[str] = None,
    dry_run: bool = False,
) -> KGArtifact
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `events_path` | `str \| Path` | required | Path to the input `events.jsonl` file. |
| `run_id` | `str` | required | Unique identifier for this execution run. Written into every node and edge. |
| `output_dir` | `str \| Path \| None` | `None` | Directory to write `kg.jsonld` into. When `None` the artifact is returned in memory only. |
| `ontology_path` | `str \| None` | `None` | Explicit path to `mas-ontology.ttl`. Omit to use the vendored copy or `oxp-ontology` if installed. |
| `dry_run` | `bool` | `False` | Parse and validate but do not write output. |

### Returns

`KGArtifact` containing the normalised KG.  If `output_dir` is provided and
`dry_run` is `False`, the artifact is also saved to `<output_dir>/kg.jsonld`.

### Examples

**Minimal — in-memory only:**

```python
from mas.library.kg.steps import run_normalize

artifact = run_normalize("events.jsonl", run_id="run-001")
print(artifact)
# KGArtifact(nodes=42, edges=61, run_id='run-001')
```

**Write kg.jsonld to a run directory:**

```python
from pathlib import Path
from mas.library.kg.steps import run_normalize

artifact = run_normalize(
    "data/run-001/events.jsonl",
    run_id="run-001",
    output_dir="data/run-001",
)
# → data/run-001/kg.jsonld written
print(artifact.node_count, artifact.edge_count)
```

**Custom ontology + dry-run:**

```python
artifact = run_normalize(
    "events.jsonl",
    run_id="test-run",
    ontology_path="/opt/ontologies/mas-ontology.ttl",
    dry_run=True,
)
# Parses + validates; nothing written to disk.
```

---

## 2. `run_normalize_otel` — OTel spans → KGArtifact

**Module:** `mas.library.kg.steps.normalize_otel`

### Signature

```python
from mas.library.kg.steps import run_normalize_otel

def run_normalize_otel(
    spans_path: str | Path,
    run_id: str,
    output_dir: Optional[str | Path] = None,
    *,
    ontology_path: Optional[str] = None,
    strict: bool = True,
    synthesize_llm_gaps: bool = True,
    write_events: bool = True,
    dry_run: bool = False,
) -> KGArtifact
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `spans_path` | `str \| Path` | required | Path to the OTel spans JSON file (a JSON array of span dicts). |
| `run_id` | `str` | required | Unique identifier for this execution run. |
| `output_dir` | `str \| Path \| None` | `None` | Directory to write `events.jsonl` and `kg.jsonld` into. |
| `ontology_path` | `str \| None` | `None` | Explicit path to `mas-ontology.ttl`. |
| `strict` | `bool` | `True` | Raise on unknown span types encountered during Stage 1 conversion. |
| `synthesize_llm_gaps` | `bool` | `True` | Add synthetic `llm_call` events for agents with no child LLM span. |
| `write_events` | `bool` | `True` | Also write the intermediate `events.jsonl` to `output_dir`. |
| `dry_run` | `bool` | `False` | Convert but do not write any output. |

### Returns

`KGArtifact` containing the normalised KG.  Two extra metadata keys are set:

- `metadata["event_count"]` — number of events produced by Stage 1.
- `metadata["otel_format"]` — detected wire format: `"openclaw"`, `"ioa_observe"`, or `"mas_sdk_legacy"`.

### Examples

**Basic OTel → KG:**

```python
from mas.library.kg.steps import run_normalize_otel

artifact = run_normalize_otel(
    "traces/run-001.otel.json",
    run_id="run-001",
    output_dir="data/run-001",
)
print(artifact.metadata["otel_format"])   # e.g. "ioa_observe"
print(artifact.metadata["event_count"])   # e.g. 18
```

**Skip writing intermediate events.jsonl:**

```python
artifact = run_normalize_otel(
    "traces/run-001.otel.json",
    run_id="run-001",
    output_dir="data/run-001",
    write_events=False,
)
# Only kg.jsonld is written; events.jsonl is produced in memory then discarded.
```

**Lenient mode for exploratory work:**

```python
artifact = run_normalize_otel(
    "traces/experiment.otel.json",
    run_id="experiment-42",
    strict=False,                # unknown span types are silently skipped
    synthesize_llm_gaps=False,   # no gap-fill synthesis
    dry_run=True,
)
```

---

## 3. `run_validate_kg` — structural + SHACL validation

**Module:** `mas.library.kg.steps.validate_kg`

### Signature

```python
from mas.library.kg.steps import run_validate_kg

def run_validate_kg(
    artifact: KGArtifact | str | Path,
    *,
    ontology_path: Optional[str] = None,
    strict: bool = False,
    fail_on_error: bool = False,
    checks: Optional[list[str]] = None,
) -> dict
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artifact` | `KGArtifact \| str \| Path` | required | The KG to validate. |
| `ontology_path` | `str \| None` | `None` | Path to `mas-ontology.ttl` for SHACL validation. |
| `strict` | `bool` | `False` | Treat recommended-attribute gaps as errors. |
| `fail_on_error` | `bool` | `False` | Raise `ValueError` if any errors are found. |
| `checks` | `list[str] \| None` | `None` | Subset of check names to run. `None` runs all. |

**Available check names:** `unknown_node_types`, `unknown_edge_types`,
`block_vocabulary`, `layer_vocabulary`, `shacl`.

### Returns

```python
{
    "error_count":   int,
    "warning_count": int,
    "results": [
        {"check": str, "status": str, "detail": str},
        ...
    ],
}
```

`status` is `"pass"`, `"error"`, or `"warning"`.

### Examples

**Validate an on-disk KG:**

```python
from mas.library.kg.steps import run_validate_kg

report = run_validate_kg("data/run-001/kg.jsonld")
print(report["error_count"], report["warning_count"])
for r in report["results"]:
    if r["status"] != "pass":
        print(f"  [{r['status']}] {r['check']}: {r['detail']}")
```

**Validate an in-memory artifact, strict mode:**

```python
report = run_validate_kg(artifact, strict=True, fail_on_error=True)
# Raises ValueError if any check finds an error or missing recommended attribute.
```

**Run only a specific subset of checks:**

```python
report = run_validate_kg(
    artifact,
    checks=["containment_chain", "temporal_enclosure", "unknown_node_types"],
)
```

---

## 4. `run_verify_events` — events.jsonl validation

**Module:** `mas.library.kg.steps.verify_events`

Note: this step operates on the intermediate `events.jsonl` format, not on a
`KGArtifact`.  It takes a file path rather than `KGArtifact | str | Path`.

### Signature

```python
from mas.library.kg.steps import run_verify_events

def run_verify_events(
    events_path: str | Path,
    *,
    strictness: Literal["required", "recommended", "complete"] = "required",
    fail_on_error: bool = False,
) -> dict
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `events_path` | `str \| Path` | required | Path to `events.jsonl`. |
| `strictness` | `"required" \| "recommended" \| "complete"` | `"required"` | Validation depth. `"required"` checks only mandatory fields; `"recommended"` adds warnings; `"complete"` enforces every rule. |
| `fail_on_error` | `bool` | `False` | Raise `ValueError` if any errors are found. |

### Returns

```python
{
    "error_count":   int,
    "warning_count": int,
    "event_count":   int,
    "violations": [
        {
            "level":    str,
            "severity": str,   # "error" | "warning"
            "rule":     str,
            "message":  str,
            "kind":     str,
            "line":     int,
            "field":    str,
        },
        ...
    ],
}
```

### Examples

**Basic — errors only:**

```python
from mas.library.kg.steps import run_verify_events

report = run_verify_events("data/run-001/events.jsonl")
print(f"{report['event_count']} events, {report['error_count']} errors")
```

**Recommended strictness with abort-on-error:**

```python
report = run_verify_events(
    "data/run-001/events.jsonl",
    strictness="recommended",
    fail_on_error=True,
)
# Raises ValueError if any error-level violation is found.
```

**Inspect individual violations:**

```python
report = run_verify_events("events.jsonl", strictness="complete")
for v in report["violations"]:
    print(f"  line {v['line']} [{v['severity']}] {v['rule']}: {v['message']}")
```

---

## 5. `run_annotate` — generic KG node annotation

**Module:** `mas.library.kg.steps.annotate`

### Signature

```python
from mas.library.kg.steps import run_annotate

def run_annotate(
    artifact: KGArtifact | str | Path,
    value_fn: Callable[[dict], dict | None],
    *,
    node_type: str,
    edge_name: str,
    annotation_node_type: str = "Annotation",
    output_path: Optional[str | Path] = None,
    dry_run: bool = False,
) -> KGArtifact
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artifact` | `KGArtifact \| str \| Path` | required | Input KG. When a path is given and `output_path` is `None`, the input file is overwritten. |
| `value_fn` | `Callable[[dict], dict \| None]` | required | Called with each matching node. Return a dict of annotation fields to attach, or `None` to skip this node. |
| `node_type` | `str` | required | Only nodes with `node["node_type"] == node_type` are processed. |
| `edge_name` | `str` | required | Edge type added from source node to annotation node (e.g. `"hasEmbedding"`). |
| `annotation_node_type` | `str` | `"Annotation"` | `node_type` for the new annotation nodes. |
| `output_path` | `str \| Path \| None` | `None` | Write enriched KG here. Overrides the default overwrite behaviour. |
| `dry_run` | `bool` | `False` | Compute annotations but do not write output. |

### Returns

The enriched `KGArtifact` (original + new annotation nodes and edges).
`value_fn` is responsible for the external computation; the step only manages
graph structure.

### Examples

**Embedding State nodes with OpenAI:**

```python
import openai
from mas.library.kg.steps import run_annotate

client = openai.OpenAI()

def embed_fn(node: dict):
    content = node.get("content", "").strip()
    if not content:
        return None
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=[content],
    )
    return {
        "vector":     resp.data[0].embedding,
        "model":      "text-embedding-3-small",
        "dimensions": 1536,
    }

enriched = run_annotate(
    "data/run-001/kg.jsonld",
    embed_fn,
    node_type="State",
    edge_name="hasEmbedding",
    annotation_node_type="StateEmbedding",
)
# Overwrites data/run-001/kg.jsonld with the enriched version.
```

**Write to a separate file:**

```python
enriched = run_annotate(
    artifact,           # KGArtifact already in memory
    embed_fn,
    node_type="State",
    edge_name="hasEmbedding",
    output_path="data/run-001/kg-embedded.json",
)
```

**Custom scoring annotation (no side-effects on disk):**

```python
def score_fn(node: dict):
    # Assign a heuristic quality score to LLMCall nodes.
    tokens = node.get("completion_tokens", 0)
    return {"quality_score": min(1.0, tokens / 500)} if tokens else None

scored = run_annotate(
    artifact,
    score_fn,
    node_type="LLMCall",
    edge_name="hasQualityScore",
    annotation_node_type="QualityAnnotation",
    dry_run=True,  # inspect result without writing
)
print(f"Added {scored.node_count - artifact.node_count} score nodes")
```

---

## 6. `run_compare_kg` — structural parity comparison

**Module:** `mas.library.kg.steps.compare_kg`

### Signature

```python
from mas.library.kg.steps import run_compare_kg

def run_compare_kg(
    candidate: KGArtifact | str | Path,
    reference: KGArtifact | str | Path,
    *,
    strict: bool = False,
    fail_on_error: bool = False,
    output_path: Optional[str | Path] = None,
) -> dict
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `candidate` | `KGArtifact \| str \| Path` | required | Candidate KG (system under test). |
| `reference` | `KGArtifact \| str \| Path` | required | Reference KG (ground truth). |
| `strict` | `bool` | `False` | Count element-level diff failures as comparison failures. |
| `fail_on_error` | `bool` | `False` | Raise `RuntimeError` if the comparison fails. |
| `output_path` | `str \| Path \| None` | `None` | Write the parity report JSON to this path. |

### Returns

```python
{
    "passed":  bool,
    "checks":  [{"name": str, "passed": bool, "message": str}, ...],
    "summary": {"total_checks": int, "passed": int, "failed": int},
    "reference_stats":  {...},
    "candidate_stats":  {...},
    # when inputs were file paths:
    "candidate_path":   str,
    "reference_path":   str,
    # when output_path is set:
    "report_path":      str,
}
```

Runs seven structural checks: `agent_coverage`, `node_distribution`,
`edge_distribution`, `call_depth`, `tool_coverage`, `delegation_topology`,
`element_level_diff`.

### Examples

**Compare two on-disk KGs:**

```python
from mas.library.kg.steps import run_compare_kg

report = run_compare_kg(
    "data/run-001/kg.jsonld",
    "data/reference/kg.jsonld",
    output_path="data/run-001/parity_report.json",
)
print("PASS" if report["passed"] else "FAIL")
for c in report["checks"]:
    status = "✓" if c["passed"] else "✗"
    print(f"  {status} {c['name']}: {c.get('message', '')}")
```

**Compare in-memory artifacts, abort on failure:**

```python
report = run_compare_kg(
    candidate_artifact,
    reference_artifact,
    strict=True,
    fail_on_error=True,
)
# Raises RuntimeError if any check fails.
```

**Inspect per-check stats:**

```python
report = run_compare_kg(candidate_artifact, reference_artifact)
print(report["summary"])
# {"total_checks": 7, "passed": 6, "failed": 1}
print(report["candidate_stats"])
# {"node_count": 42, "edge_count": 61, "agent_ids": [...], ...}
```

---

## 7. `run_neo4j_push` — push KG to Neo4j

**Module:** `mas.library.kg.steps.neo4j_push`

Requires the `[neo4j]` extra:

```bash
uv pip install "mas-library-kg[neo4j]"
```

### Signature

```python
from mas.library.kg.steps import run_neo4j_push

def run_neo4j_push(
    artifact: KGArtifact | str | Path,
    *,
    uri: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    password_env: Optional[str] = None,
    database: Optional[str] = None,
    batch_size: int = 200,
    app_name: str = "",
    source: str = "mas-lab",
    annotations: Optional[dict] = None,
    clear_session: bool = False,
    ensure_indexes: bool = True,
    dry_run: bool = False,
) -> dict
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artifact` | `KGArtifact \| str \| Path` | required | KG to push. |
| `uri` | `str \| None` | `None` | Bolt URI. Falls back to `NEO4J_URI` env var, then `bolt://localhost:7687`. |
| `username` | `str \| None` | `None` | Neo4j username. Falls back to `NEO4J_USER`. |
| `password` | `str \| None` | `None` | Literal password. Prefer `password_env` for credentials not hard-coded in source. |
| `password_env` | `str \| None` | `None` | Name of the env var holding the password (e.g. `"MY_NEO4J_PW"`). Falls back to `NEO4J_PASSWORD`. |
| `database` | `str \| None` | `None` | Target database name. Falls back to `NEO4J_DB_AGENT`, then `"neo4j"`. |
| `batch_size` | `int` | `200` | UNWIND batch size for Cypher writes. |
| `app_name` | `str` | `""` | Written as `appId` on every node and edge. |
| `source` | `str` | `"mas-lab"` | Data-origin marker written to every element. |
| `annotations` | `dict \| None` | `None` | Extra attributes merged onto every element before pushing. |
| `clear_session` | `bool` | `False` | Delete all existing nodes for this session before pushing. |
| `ensure_indexes` | `bool` | `True` | Create covering indexes before writing (safe to call repeatedly). |
| `dry_run` | `bool` | `False` | Build Cypher but do not connect to Neo4j. |

### Returns

```python
{
    "rows":     int,   # Cypher rows affected
    "nodes":    int,
    "edges":    int,
    "uri":      str,
    # when input was a file path:
    "kg_path":  str,
}
```

### Examples

**Env-var credentials (recommended):**

```bash
export NEO4J_URI=bolt://neo4j.example.com:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=secret
export NEO4J_DB_AGENT=mas
```

```python
from mas.library.kg.steps import run_neo4j_push

result = run_neo4j_push("data/run-001/kg.jsonld", app_name="my-agent-app")
print(result)
# {"rows": 103, "nodes": 42, "edges": 61, "uri": "bolt://neo4j.example.com:7687", ...}
```

**Explicit connection with `password_env`:**

```python
result = run_neo4j_push(
    artifact,
    uri="bolt://neo4j.internal:7687",
    username="neo4j",
    password_env="MY_NEO4J_SECRET",   # reads os.environ["MY_NEO4J_SECRET"]
    database="mas-runs",
    app_name="my-agent-app",
    source="lab-experiment-7",
)
```

**Literal password (testing / local dev only):**

```python
result = run_neo4j_push(
    artifact,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="localpassword",
    database="neo4j",
    clear_session=True,   # wipe previous session data first
    dry_run=False,
)
```

---

## 8. `run_neo4j_dump` — fetch KG from Neo4j

**Module:** `mas.library.kg.steps.neo4j_dump`

Requires the `[neo4j]` extra.

### Signature

```python
from mas.library.kg.steps import run_neo4j_dump

def run_neo4j_dump(
    *,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    uri: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    password_env: Optional[str] = None,
    database: Optional[str] = None,
) -> KGArtifact
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | `str \| None` | `None` | Session ID to retrieve (preferred over `run_id`). |
| `run_id` | `str \| None` | `None` | Run ID to retrieve (used when `session_id` is absent). At least one of `session_id` or `run_id` must be provided. |
| `output_path` | `str \| Path \| None` | `None` | If given, save the fetched `KGArtifact` to this path. |
| `uri` | `str \| None` | `None` | Bolt URI. Falls back to `NEO4J_URI`, then `bolt://localhost:7687`. |
| `username` | `str \| None` | `None` | Falls back to `NEO4J_USER`. |
| `password` | `str \| None` | `None` | Literal password. Prefer `password_env`. |
| `password_env` | `str \| None` | `None` | Env var name holding the password. Falls back to `NEO4J_PASSWORD`. |
| `database` | `str \| None` | `None` | Falls back to `NEO4J_DB_AGENT`, then `"neo4j"`. |

### Returns

`KGArtifact` reconstructed from Neo4j.  Raises `ValueError` if neither
`session_id` nor `run_id` is provided.

### Examples

**Fetch by session ID (env-var credentials):**

```python
from mas.library.kg.steps import run_neo4j_dump

artifact = run_neo4j_dump(session_id="sess-abc-001")
print(artifact)
# KGArtifact(nodes=42, edges=61, run_id='run-001')
```

**Fetch by run ID and save to disk:**

```python
artifact = run_neo4j_dump(
    run_id="run-001",
    output_path="recovered/run-001/kg.jsonld",
)
```

**Explicit credentials with `password_env`:**

```python
artifact = run_neo4j_dump(
    session_id="sess-abc-001",
    uri="bolt://neo4j.internal:7687",
    username="neo4j",
    password_env="MY_NEO4J_SECRET",
    database="mas-runs",
    output_path="backup/sess-abc-001.kg.jsonld",
)
```

---

## Streaming / batching multiple KGs

Use `stream_artifacts` to lazily iterate over many `kg.jsonld` files without
loading all of them into memory at once.  Combine it with step functions that
accept `KGArtifact` directly:

```python
from pathlib import Path
from mas.library.kg.artifact import stream_artifacts
from mas.library.kg.steps import run_validate_kg, run_neo4j_push

run_dir = Path("data/experiment-42")

# Collect all run output directories
kg_paths = sorted(run_dir.glob("*/kg.jsonld"))

for artifact in stream_artifacts(kg_paths):
    run_id = artifact.run_id() or "unknown"

    # Validate each KG
    report = run_validate_kg(artifact, strict=False)
    if report["error_count"]:
        print(f"[{run_id}] validation FAILED: {report['error_count']} errors")
        continue

    # Push clean KGs to Neo4j
    result = run_neo4j_push(artifact, app_name="batch-upload", source="experiment-42")
    print(f"[{run_id}] pushed {result['nodes']} nodes, {result['edges']} edges")
```

`stream_artifacts` accepts any iterable of paths — glob results, a manifest
file read line-by-line, or a list constructed at runtime:

```python
from mas.library.kg.artifact import stream_artifacts

paths = [f"runs/{i:04d}/kg.jsonld" for i in range(1, 201)]
for art in stream_artifacts(paths):
    ...
```

---

## Chaining steps

The step functions compose naturally because KG-producing steps return
`KGArtifact` and KG-consuming steps accept `KGArtifact | str | Path`.
No intermediate files are required.

The example below is a complete pipeline:

1. **OTel → KG** via `run_normalize_otel`
2. **Validate events** via `run_verify_events` (requires path — written by step 1)
3. **Validate KG** via `run_validate_kg`
4. **Compare** against a reference KG via `run_compare_kg`
5. **Push** to Neo4j via `run_neo4j_push`

```python
from pathlib import Path
from mas.library.kg.steps import (
    run_normalize_otel,
    run_verify_events,
    run_validate_kg,
    run_compare_kg,
    run_neo4j_push,
)

SPANS_PATH    = Path("traces/run-007.otel.json")
REFERENCE_KG  = Path("reference/kg.jsonld")
OUTPUT_DIR    = Path("data/run-007")
RUN_ID        = "run-007"

# ── Step 1: OTel → KG ────────────────────────────────────────────────────────
artifact = run_normalize_otel(
    SPANS_PATH,
    run_id=RUN_ID,
    output_dir=OUTPUT_DIR,   # writes events.jsonl + kg.jsonld
    strict=True,
)
print(f"Normalized: {artifact.node_count} nodes, {artifact.edge_count} edges")
print(f"OTel format: {artifact.metadata['otel_format']}")

# ── Step 2: Verify events (path-based, file written by step 1) ────────────────
events_report = run_verify_events(
    OUTPUT_DIR / "events.jsonl",
    strictness="recommended",
)
if events_report["error_count"]:
    raise RuntimeError(f"events.jsonl has {events_report['error_count']} errors")
print(f"Events OK: {events_report['event_count']} events verified")

# ── Step 3: Validate KG (in-memory artifact, no re-read from disk) ────────────
kg_report = run_validate_kg(
    artifact,                # pass the KGArtifact directly
    strict=False,
    fail_on_error=True,
)
print(f"KG validation: {kg_report['error_count']} errors, {kg_report['warning_count']} warnings")

# ── Step 4: Compare against reference ────────────────────────────────────────
parity = run_compare_kg(
    artifact,                # KGArtifact
    REFERENCE_KG,            # loaded from disk on demand
    output_path=OUTPUT_DIR / "parity_report.json",
)
print(f"Parity: {'PASS' if parity['passed'] else 'FAIL'} "
      f"({parity['summary']['passed']}/{parity['summary']['total_checks']})")

# ── Step 5: Push to Neo4j ─────────────────────────────────────────────────────
push_result = run_neo4j_push(
    artifact,
    app_name="my-experiment",
    source="run-007",
    # Connection from env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DB_AGENT
)
print(f"Pushed: {push_result['nodes']} nodes, {push_result['edges']} edges → {push_result['uri']}")
```

### Batch pipeline across many runs

```python
from pathlib import Path
from mas.library.kg.artifact import stream_artifacts
from mas.library.kg.steps import run_validate_kg, run_compare_kg, run_neo4j_push

REFERENCE = Path("reference/kg.jsonld")
RUNS      = sorted(Path("data").glob("run-*/kg.jsonld"))

passed = failed = 0

for artifact in stream_artifacts(RUNS):
    rid = artifact.run_id() or "?"

    val = run_validate_kg(artifact)
    if val["error_count"]:
        print(f"[{rid}] INVALID — skipping")
        failed += 1
        continue

    cmp = run_compare_kg(artifact, REFERENCE)
    if not cmp["passed"]:
        print(f"[{rid}] PARITY FAIL")
        failed += 1
        continue

    run_neo4j_push(artifact, source="batch")
    print(f"[{rid}] OK — pushed {artifact.node_count}N {artifact.edge_count}E")
    passed += 1

print(f"\n{passed} passed, {failed} failed")
```

---

## Pipeline YAML

For declarative pipelines the same step logic is available via
`mas-lab-graph`'s `PipelineStep` adapters.  All parameters map
one-to-one with the Python function signatures shown above.

See [`pipelines/README.md`](../pipelines/README.md) for the full catalog
of bundled YAML pipelines and how to reference them from a benchmark run.

Example: run the bundled `native-to-kg` pipeline from a benchmark config:

```yaml
run:
  post:
    - ref: kg:native-to-kg
    - ref: kg:compare-two-kg
```
