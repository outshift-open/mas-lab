# Tutorial: From Trace to Knowledge Graph

MAS-Lab [Tutorial 9](../../docs/tutorials/09-kg-oxp/README.md) is the
hands-on KG & OXP path (native→KG, OTel→KG, Neo4j, equivalence). This page is
the library-kg deep dive: Neo4j push/dump and KG compare.

A worked example that follows a concrete multi-agent trace end-to-end: raw event
logs → knowledge graph → Neo4j → round-trip dump → diff.  Every `mas-lab graph`
command is shown alongside the library function it calls, so you can drop down to
Python whenever the CLI shortcuts aren't enough.

**What you need**

- `mas-lab` installed
- Docker (for the Neo4j instance) — `library-kg/docker/compose.yaml`
- The sample files in `library-kg/examples/trip-planner/` (MAS) and
  `library-kg/examples/qa-agent/` (Tutorial 1 qa-agent, used by Tutorial 9)

**Reference docs used in this tutorial**

| Topic | Doc |
|---|---|
| Step functions | [steps.md](steps.md) |
| Neo4j push / dump / denormalize | [neo4j.md](neo4j.md) |
| KG structural comparison | [kg-compare.md](kg-compare.md) |
| KGIndex / FacetQuery | [kg-query.md](kg-query.md) |
| Spec injection | [kg-spec.md](kg-spec.md) |
| Node annotation | [annotation.md](annotation.md) |

---

## The scenario

`trip-planner` is a two-agent MAS: `planner` receives the user request and routes
it; `itinerary_agent` fans out two parallel sub-tasks (flight search + hotel RAG
query) and synthesises the answer.

One run of this system produces a trace file — `events.jsonl`.  Our goal is to
turn that trace into a structured knowledge graph, store it in Neo4j, and verify
that nothing was lost in transit.

---

## Sample files

```
library-kg/examples/
├── trip-planner/
│   ├── events.jsonl       # native MAS event trace  (20 events)
│   └── otel_spans.jsonl   # same trace as OTel SDK spans (6 spans)
├── infra/
│   └── neo4j-local.yaml   # Datastore infra manifest
└── pipeline/
    └── trip-planner.yaml  # equivalent declarative pipeline
```

### `events.jsonl` (abbreviated)

```jsonl
{"kind":"user_input","agent_id":"mas","call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","content":"Plan a 3-day trip to Paris…","timestamp":1716199999.5}
{"kind":"mas_call_start","agent_id":"mas","call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","timestamp":1716200000.0}
{"kind":"execution_start","agent_id":"planner","call_id":"tp-exec-001","parent_call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","boundary":"AgentCall","timestamp":1716200001.0,"input":"Plan a 3-day trip to Paris…"}
{"kind":"governance_checked","hook":"pre_agent_communication","plugin":"RoutingPlugin","contract_id":"routing","reason":"planner → itinerary_agent: found in declared edges","timestamp":1716200003.8}
{"kind":"parallel_group_start","agent_id":"itinerary_agent","call_id":"tp-pg-001","parent_call_id":"tp-exec-002","branch_count":2,"branches":["flights","hotels"],"timestamp":1716200005.0}
{"kind":"tool_call_end","agent_id":"itinerary_agent","call_id":"tp-tc-001","tool_name":"search_flights","status":"success","result":{"flights":[{"id":"AF101","price_usd":680}]},"timestamp":1716200006.5}
{"kind":"rag_query_end","agent_id":"itinerary_agent","call_id":"tp-rag-001","status":"success","retrieved_doc_count":4,"timestamp":1716200006.8}
{"kind":"mas_call_end","agent_id":"mas","call_id":"tp-mas-001","session_id":"trip-planner/demo/baseline/item1/r1","status":"success","timestamp":1716200010.0}
```

The full 20-event file is at `examples/trip-planner/events.jsonl`.  Each event has
a `kind`, `agent_id`, `call_id`, optional `parent_call_id`, and a `session_id`
that encodes the lab hierarchy: `{lab}/{experiment}/{scenario}/{item}/{run}`.

### `otel_spans.jsonl` (alternative input)

If your system emits OpenTelemetry traces instead, the same trace is available as
OTel SDK spans in `examples/trip-planner/otel_spans.jsonl`.  Each span carries
`mas.boundary` and `mas.agent.id` attributes; the normaliser handles the
span→node mapping automatically.  See [§ OTel path](#3-otel-path) below.

---

## 1. Infrastructure setup

### 1a. Write an infra manifest

`mas-lab graph push` and `mas-lab graph dump` accept a `--to` / `--from` flag
that names a *store ID* defined in your workspace infra manifest.  This keeps
connection details out of your shell history and makes it easy to switch between
local, staging, and production targets.

Create `examples/infra/neo4j-local.yaml`:

```yaml
apiVersion: infra/v1
kind: Datastore

metadata:
  name: neo4j-local
  description: Local Neo4j 5 instance (Docker) for development.

spec:
  stores:
    neo4j-local:
      type: neo4j
      uri: bolt://localhost:7687
      user: neo4j
      password_env: NEO4J_PASSWORD   # env var name — never the value itself
      database: neo4j
```

Place this file anywhere on the path that `mas-lab` searches for infra manifests
(typically `infra/` in your workspace root, or the directory you pass via
`--infra`).  The full manifest is at `examples/infra/neo4j-local.yaml`.

> **Reference** — DatastoreSpec fields, store resolution, InfraBundle merging:
> [neo4j.md → Infra manifest](neo4j.md#infra-manifest)

### 1b. Start Neo4j

```bash
export NEO4J_PASSWORD=a-strong-password   # min 8 chars for Neo4j 5

# Option A — via mas-lab-services (recommended)
mas-lab services start neo4j

# Option B — direct Docker Compose
docker compose \
  -f mas-lab-services/src/mas/lab/services/catalogue/neo4j/docker-compose.yml \
  up -d
```

Neo4j Browser is at <http://localhost:7474> (login: `neo4j` / `$NEO4J_PASSWORD`).
The Bolt endpoint is at `bolt://localhost:7687`.

Wait for the health-check to pass before pushing:

```bash
docker compose \
  -f mas-lab-services/src/mas/lab/services/catalogue/neo4j/docker-compose.yml \
  ps
# neo4j   running (healthy)
```

---

## 2. Validate native events

Before normalization it's worth checking that `events.jsonl` is well-formed:
all required fields present, event kinds recognized, parent/child call IDs
consistent.  This is the **`verify_events`** step.

```bash
# No CLI command — use Python directly (or include as a pipeline step)
python - <<'EOF'
from mas.library.kg.steps import run_verify_events

result = run_verify_events(
    "examples/trip-planner/events.jsonl",
    strictness="recommended",   # "required" | "recommended" | "complete"
)
print(f"{result['event_count']} events — "
      f"{result['error_count']} errors, {result['warning_count']} warnings")
for v in result["violations"]:
    print(f"  [{v['severity'].upper()}] {v['message']}")
EOF
```

Expected output for the sample file:

```
20 events — 0 errors, 0 warnings
```

> **Reference** — `run_verify_events` parameters, violation structure, strictness
> levels: [steps.md → run_verify_events](steps.md#run_verify_events)

**As a pipeline step:**

```yaml
- name: verify
  type: verify_events
  config:
    strictness: recommended
    fail_on_error: true
```

---

## 3. Normalize events → KG

Normalization reads `events.jsonl`, maps each event to ontology-typed nodes and
edges, resolves call containment, and writes a `kg.jsonld` artifact.

```bash
mas-lab graph normalize \
  examples/trip-planner/events.jsonl \
  --output examples/trip-planner/kg.jsonld \
  --session-id trip-planner/demo/baseline/item1/r1
```

`--session-id` encodes the lab hierarchy `{lab}/{experiment}/{scenario}/{item}/{run}`.
When the trace sits under a `lab-config.yaml` the value is derived automatically;
pass it explicitly when working outside a lab directory.

The command prints a summary:

```
normalized 20 events → 18 nodes, 22 edges
  session_id : trip-planner/demo/baseline/item1/r1
  run_id     : r1
  written    : examples/trip-planner/kg.jsonld
```

The output `kg.jsonld` is a **[`KGArtifact`](steps.md#kgartifact)** serialised as JSON:

```json
{
  "run_id": "r1",
  "metadata": {
    "event_count": 20,
    "session_id": "trip-planner/demo/baseline/item1/r1",
    "source": "native"
  },
  "nodes": [
    { "id": "tp-mas-001", "node_type": "MASCall", "agentId": "mas", ... },
    { "id": "tp-exec-001", "node_type": "AgentCall", "agentId": "planner", ... },
    ...
  ],
  "edges": [
    { "edge_type": "contains", "from_id": "tp-mas-001", "to_id": "tp-exec-001" },
    ...
  ]
}
```

**What this command actually does** — it is a thin wrapper around
[`run_normalize`](steps.md#run_normalize):

```python
from mas.library.kg.steps import run_normalize

artifact = run_normalize(
    "examples/trip-planner/events.jsonl",
    run_id="r1",
    output_dir="examples/trip-planner/",
    session_id="trip-planner/demo/baseline/item1/r1",
)
# artifact is a KGArtifact — artifact.nodes, artifact.edges, artifact.metadata
artifact.save("examples/trip-planner/kg.jsonld")
```

`run_normalize` in turn calls
`mas.library.kg.core.graph_builder.normalize_events` to do the
ontology-driven mapping.

---

## 3. OTel path

If your system emits OpenTelemetry spans instead of native events, pass `--otel`:

```bash
mas-lab graph normalize \
  examples/trip-planner/otel_spans.jsonl \
  --otel \
  --output examples/trip-planner/kg-from-otel.json \
  --session-id trip-planner/demo/baseline/item1/r1
```

The OTel normaliser maps `mas.boundary` span attribute → node type, resolves
parent/child span relationships into containment edges, and produces a `kg.jsonld`
structurally identical to the native output.

You can also convert native events to OTel format first, then normalize:

```bash
# Step A: convert events → OTel spans
mas-lab graph events-to-otel \
  examples/trip-planner/events.jsonl \
  --output examples/trip-planner/converted_spans.jsonl \
  --service-name trip-planner

# Step B: normalize the spans
mas-lab graph normalize \
  examples/trip-planner/converted_spans.jsonl \
  --otel \
  --output examples/trip-planner/kg-from-converted.json
```

**Python equivalent:**

```python
from mas.library.kg.steps import run_normalize_otel

artifact = run_normalize_otel(
    "examples/trip-planner/otel_spans.jsonl",
    run_id="r1",
    output_dir="examples/trip-planner/",
    session_id="trip-planner/demo/baseline/item1/r1",
)
```

> **Reference** — OTel span format, attribute mapping, span→node type table:
> [steps.md → run_normalize_otel](steps.md#run_normalize_otel)

---

## 4. Verify the KG

With `kg.jsonld` in hand, run structural validation.  This checks ontology
vocabulary, containment chain integrity, temporal enclosure, session
connectivity, and optionally SHACL constraints.

```bash
mas-lab graph validate examples/trip-planner/kg.jsonld
```

Output:

```
✓ containment_chain     pass
✓ state_nesting         pass
✓ processing_call_gate  pass
✓ temporal_enclosure    pass
✓ session_connectivity  pass
✓ unknown_node_types    pass
✓ unknown_edge_types    pass

18 nodes, 22 edges — 0 errors, 0 warnings
```

Run with `--strict` to also check recommended-attribute gaps, and `--fail` to
exit non-zero on any error (useful in CI):

```bash
mas-lab graph validate examples/trip-planner/kg.jsonld --strict --fail
```

**Python equivalent:**

```python
from mas.library.kg.steps import run_validate_kg

report = run_validate_kg(
    "examples/trip-planner/kg.jsonld",
    strict=False,
    fail_on_error=True,
    checks=["containment_chain", "session_connectivity", "unknown_node_types"],
)
print(report["error_count"], "errors")
```

> **Reference** — all available check names, violation format, SHACL integration:
> [steps.md → run_validate_kg](steps.md#run_validate_kg)

---

## 5. Push to Neo4j

Push `kg.jsonld` to the local Neo4j instance.  The `--to` flag names the store ID
from your infra manifest (`neo4j-local` from `examples/infra/neo4j-local.yaml`):

```bash
mas-lab graph push \
  examples/trip-planner/kg.jsonld \
  --to neo4j-local
```

The push is **idempotent** — it uses Cypher `MERGE` semantics, so running it twice
leaves the graph unchanged.  Output:

```
pushed trip-planner/demo/baseline/item1/r1
  nodes merged : 18
  edges merged : 22
  elapsed      : 0.4 s
```

Without a manifest you can pass connection flags directly:

```bash
mas-lab graph push \
  examples/trip-planner/kg.jsonld \
  --uri bolt://localhost:7687 \
  --user neo4j
  # prompts for NEO4J_PASSWORD if not set in env
```

Use `--dry-run` to preview the generated Cypher without connecting:

```bash
mas-lab graph push examples/trip-planner/kg.jsonld --to neo4j-local --dry-run
```

**What this command does** — after loading the `KGArtifact` it calls
[`push_kg_to_neo4j`](neo4j.md#push_kg_to_neo4j) from `mas.library.kg.neo4j`:

```python
from mas.library.kg.artifact import KGArtifact

artifact = KGArtifact.from_file("examples/trip-planner/kg.jsonld")
result = artifact.push_to_neo4j(
    uri="bolt://localhost:7687",
    username="neo4j",
    password="...",
    database="neo4j",
)
print(result["node_count"], "nodes,", result["edge_count"], "edges")
```

Under the hood `push_to_neo4j` calls
[`build_merge_statements`](neo4j.md#build_merge_statements) to generate
parameterised `UNWIND $rows AS row MERGE …` Cypher, then executes it in batches
of 200.  Every node gets a `KGNode` secondary label in addition to its semantic
type, enabling cross-label lookups.

> **Reference** — UNWIND batching, KGNode secondary label, `_JSON_PREFIX` prop
> encoding, index creation: [neo4j.md → push_kg_to_neo4j](neo4j.md#push_kg_to_neo4j)

---

## 6. Browse in Neo4j Browser

Open <http://localhost:7474> and run:

```cypher
// All nodes for our session
MATCH (n:KGNode {sessionId: "trip-planner/demo/baseline/item1/r1"})
RETURN n LIMIT 50

// The agent communication arc
MATCH path = (p:AgentCall {agentId: "planner"})-[:communicatesWith|contains*]->(i:AgentCall {agentId: "itinerary_agent"})
RETURN path

// Tool calls made by itinerary_agent
MATCH (a:AgentCall {agentId: "itinerary_agent"})-[:contains]->(t:ToolCall)
RETURN t.toolName, t.status, t.startTime
ORDER BY t.startTime
```

The parallel group (`tp-pg-001`) will appear as a node with two contained
`ToolCall` and `RAGQuery` children — the fan-out structure is fully preserved.

---

## 7. Dump from Neo4j

Fetch the session back as a `KGArtifact` JSON file:

```bash
mas-lab graph dump \
  trip-planner/demo/baseline/item1/r1 \
  --from neo4j-local \
  --output examples/trip-planner/dumped.json
```

The `--from` flag mirrors `--to` from the push step.  Output:

```
fetched trip-planner/demo/baseline/item1/r1
  nodes : 18
  edges : 22
  written : examples/trip-planner/dumped.json
```

You can also print a human-readable table or restrict to a structural subgraph:

```bash
# tabular view of execution nodes
mas-lab graph dump trip-planner/demo/baseline/item1/r1 \
  --from neo4j-local \
  --block execution \
  --format table

# dump only the trajectory (state/transition) nodes
mas-lab graph dump trip-planner/demo/baseline/item1/r1 \
  --from neo4j-local \
  --block trajectory \
  --format trajectory
```

**Python equivalent:**

```python
from mas.library.kg.steps import run_neo4j_dump

artifact = run_neo4j_dump(
    session_id="trip-planner/demo/baseline/item1/r1",
    output_path="examples/trip-planner/dumped.json",
    uri="bolt://localhost:7687",
    username="neo4j",
    password="...",
    database="neo4j",
)
print(artifact.node_count, "nodes retrieved")
```

Or via `KGArtifact.fetch_from_neo4j`:

```python
from mas.library.kg.artifact import KGArtifact

artifact = KGArtifact.fetch_from_neo4j(
    session_id="trip-planner/demo/baseline/item1/r1",
    run_id="r1",
    uri="bolt://localhost:7687",
    username="neo4j",
    password="...",
    database="neo4j",
)
```

> **Reference** — `fetch_kg_from_neo4j`, `--block` filter options, Cypher preview
> mode: [neo4j.md → fetch_kg_from_neo4j](neo4j.md#fetch_kg_from_neo4j)

---

## 8. Verify round-trip fidelity

Compare the original `kg.jsonld` to the dumped copy to ensure nothing was lost or
mutated during Neo4j push/fetch:

```bash
mas-lab graph compare \
  examples/trip-planner/dumped.json \
  --against examples/trip-planner/kg.jsonld
```

Output for a clean round-trip:

```
✓ node_count       18 == 18
✓ edge_count       22 == 22
✓ node_types       match
✓ edge_types       match
✓ session_ids      match

All checks passed — KGs are structurally equivalent.
```

**Python equivalent** using [`run_compare_kg`](steps.md#run_compare_kg):

```python
from mas.library.kg.steps import run_compare_kg

report = run_compare_kg(
    candidate="examples/trip-planner/dumped.json",
    reference="examples/trip-planner/kg.jsonld",
)
print("match:", report["match"])
for check in report["checks"]:
    status = "✓" if check["passed"] else "✗"
    print(f"  {status} {check['name']}: {check['detail']}")
```

For deeper diffs — individual missing/added nodes, property drift — use
[`compare_kg`](kg-compare.md#compare_kg) directly:

```python
from mas.library.kg.core.compare import compare_kg
from mas.library.kg.artifact import KGArtifact

candidate = KGArtifact.from_file("examples/trip-planner/dumped.json")
reference = KGArtifact.from_file("examples/trip-planner/kg.jsonld")

result = compare_kg(candidate.to_doc(), reference.to_doc())
print(result.summary())
# {match: True, node_delta: 0, edge_delta: 0, ...}
```

> **Reference** — all comparison checks, `KGCompareResult`, per-node diff:
> [kg-compare.md](kg-compare.md)

---

## 9. The `ingest` shortcut

`mas-lab graph ingest` combines normalize → validate → push in a single
idempotent command.  It reads the session ID from the lab manifest hierarchy,
checks whether the session is already in Neo4j, and skips if present:

```bash
cd path/to/my-lab/
mas-lab graph ingest examples/trip-planner/events.jsonl \
  --uri bolt://localhost:7687 \
  --yes   # skip confirmation prompt
```

On the first run:

```
session trip-planner/demo/baseline/item1/r1 not found in Neo4j
normalizing…   20 events → 18 nodes, 22 edges
pushing…       18 nodes, 22 edges merged
done
```

On subsequent runs:

```
session trip-planner/demo/baseline/item1/r1 already in Neo4j (18 nodes, 22 edges) — skipping
```

Use `mas-lab graph update` to replace an existing session (drop + re-push):

```bash
mas-lab graph update \
  examples/trip-planner/events.jsonl \
  --session-id trip-planner/demo/baseline/item1/r1 \
  --yes
```

---

## 10. Annotate the KG

After normalization you can enrich KG nodes with computed values — embeddings,
scores, labels — without re-running the normaliser.  The annotation step adds new
typed nodes and edges to the graph:

```python
from mas.library.kg.steps import run_annotate

def score_call(node):
    """Return a quality score for every AgentCall node."""
    if node.get("status") == "error":
        return {"score": 0.0, "reason": "execution_error"}
    if node.get("agentId") == "itinerary_agent":
        return {"score": 0.95, "reason": "parallel_execution_success"}
    return {"score": 0.75, "reason": "default"}

artifact = run_annotate(
    "examples/trip-planner/kg.jsonld",
    value_fn=score_call,
    node_type="AgentCall",
    edge_name="hasQualityScore",
    annotation_node_type="QualityAnnotation",
    output_path="examples/trip-planner/kg-annotated.json",
)
print(f"added {artifact.node_count - 18} annotation nodes")
```

> **Reference** — `annotate_kg_nodes`, the `value_fn` contract, batching large
> graphs: [annotation.md](annotation.md)

---

## 11. Query the KG

[`KGIndex`](kg-query.md#kgindex) builds an in-memory index for fast faceted
lookups without a database:

```python
from mas.library.kg import KGIndex
from mas.library.kg.artifact import KGArtifact

artifact = KGArtifact.from_file("examples/trip-planner/kg.jsonld")
idx = KGIndex.from_artifact(artifact)

# All tool calls made in this session
tool_calls = idx.nodes(node_type="ToolCall")
print([n["toolName"] for n in tool_calls])
# ['search_flights', 'rag_query']

# Nodes reachable from the planner's AgentCall via containment edges
planner_subtree = idx.subgraph(root_id="tp-exec-001", edge_types=["contains"])
print(planner_subtree.node_count)
```

> **Reference** — `KGIndex`, `FacetQuery`, `KGView`, streaming multiple files:
> [kg-query.md](kg-query.md)

---

## 12. Bulk ingest a benchmark run

After running a full benchmark (many traces), push all sessions at once:

```bash
mas-lab graph push-benchmark \
  --output-dir benchmark-output/ \
  --to neo4j-local \
  --workers 4
```

Check which sessions have been exported:

```bash
mas-lab graph sessions-exported \
  --output-dir benchmark-output/ \
  --to neo4j-local \
  --missing-only
```

---

## 13. The pipeline approach

Everything above can be expressed as a declarative pipeline YAML.  The pipeline
is executed by the `mas-lab-graph` pipeline runner, which instantiates the
corresponding `PipelineStep` subclass for each step type.

```yaml
# examples/pipeline/trip-planner.yaml
name: trip-planner-ingest

steps:
  - name: normalize
    type: normalize_events
    config:
      log_path: "examples/trip-planner/events.jsonl"
      session_id: trip-planner/demo/baseline/item1/r1

  - name: validate
    type: validate_kg
    depends_on: [normalize]
    config:
      fail_on_error: true

  - name: push
    type: neo4j_push
    depends_on: [validate]
    config:
      database: neo4j

  - name: dump
    type: neo4j_dump
    depends_on: [push]
    config:
      session_id: trip-planner/demo/baseline/item1/r1
      output_path: examples/trip-planner/dumped.json

  - name: compare
    type: compare_kg
    depends_on: [dump]
    config:
      candidate_step: dump
      reference_step: normalize
```

Run it:

```bash
mas-lab pipeline run examples/pipeline/trip-planner.yaml \
  --output-dir ./output/trip-planner/
```

The full annotated pipeline file is at `examples/pipeline/trip-planner.yaml`.

**CLI → pipeline step mapping**

| `mas-lab graph` command | pipeline `type` | library function |
|---|---|---|
| `normalize` | `normalize_events` | [`run_normalize`](steps.md#run_normalize) |
| `normalize --otel` | `normalize_otel` | [`run_normalize_otel`](steps.md#run_normalize_otel) |
| `validate` | `validate_kg` | [`run_validate_kg`](steps.md#run_validate_kg) |
| `push` | `neo4j_push` | [`run_neo4j_push`](steps.md#run_neo4j_push) |
| `dump` | `neo4j_dump` | [`run_neo4j_dump`](steps.md#run_neo4j_dump) |
| `compare` | `compare_kg` | [`run_compare_kg`](steps.md#run_compare_kg) |
| *(Python only)* | `verify_events` | [`run_verify_events`](steps.md#run_verify_events) |
| *(Python only)* | `annotate` | [`run_annotate`](steps.md#run_annotate) |

The CLI commands are thin wrappers: they parse flags, resolve the infra manifest,
call the library function, and format the output.  When you need programmatic
control — branching logic, conditional steps, custom error handling — import the
functions directly rather than shelling out.

---

## 14. Python walkthrough (all-in-one)

The full workflow in a single script:

```python
#!/usr/bin/env python3
"""
library-kg tutorial — full pipeline in Python.
Equivalent to running the mas-lab graph CLI commands in sequence.
"""
import os
from mas.library.kg.steps import (
    run_verify_events,
    run_normalize,
    run_validate_kg,
    run_neo4j_push,
    run_neo4j_dump,
    run_compare_kg,
)
from mas.library.kg.core.compare import compare_kg

EVENTS  = "examples/trip-planner/events.jsonl"
SESSION = "trip-planner/demo/baseline/item1/r1"
NEO4J   = dict(
    uri      = "bolt://localhost:7687",
    username = "neo4j",
    password = os.environ["NEO4J_PASSWORD"],
    database = "neo4j",
)

# ── 1. Validate events ────────────────────────────────────────────────────
result = run_verify_events(EVENTS, strictness="recommended")
assert result["error_count"] == 0, result["violations"]
print(f"✓ {result['event_count']} events valid")

# ── 2. Normalize → KGArtifact ─────────────────────────────────────────────
artifact = run_normalize(EVENTS, run_id="r1", session_id=SESSION)
print(f"✓ normalized → {artifact.node_count} nodes, {artifact.edge_count} edges")

# ── 3. Validate KG ────────────────────────────────────────────────────────
report = run_validate_kg(artifact, fail_on_error=True)
print(f"✓ KG valid ({report['error_count']} errors, {report['warning_count']} warnings)")

# ── 4. Push to Neo4j ──────────────────────────────────────────────────────
push_result = run_neo4j_push(artifact, **NEO4J)
print(f"✓ pushed {push_result['node_count']} nodes, {push_result['edge_count']} edges")

# ── 5. Dump from Neo4j ────────────────────────────────────────────────────
dumped = run_neo4j_dump(session_id=SESSION, **NEO4J)
print(f"✓ dumped {dumped.node_count} nodes, {dumped.edge_count} edges")

# ── 6. Round-trip comparison ──────────────────────────────────────────────
diff = compare_kg(dumped.to_doc(), artifact.to_doc())
assert diff.match, diff.summary()
print("✓ round-trip match")
```

---

## 15. Teardown

```bash
# Remove the session from Neo4j
mas-lab graph drop trip-planner/demo/baseline/item1/r1 \
  --uri bolt://localhost:7687 --yes

# Stop the Neo4j container (data volume persists)
docker compose \
  -f mas-lab-services/src/mas/lab/services/catalogue/neo4j/docker-compose.yml \
  down

# Stop and remove the data volume entirely
docker compose \
  -f mas-lab-services/src/mas/lab/services/catalogue/neo4j/docker-compose.yml \
  down -v
```

---

## What's next

- **Spec injection** — merge ontology-derived spec nodes into the KG to add
  contract-level context:
  [kg-spec.md](kg-spec.md)

- **Annotation** — attach embeddings, quality scores, or any computed value to
  KG nodes using a custom `value_fn`:
  [annotation.md](annotation.md)

- **Faceted queries** — use `KGIndex` and `FacetQuery` to slice and filter the
  graph in memory without Cypher:
  [kg-query.md](kg-query.md)

- **Streaming multiple artifacts** — process a full benchmark run lazily with
  `stream_artifacts(paths)`:
  [steps.md → Streaming](steps.md#streaming-multiple-artifacts)

- **Dataset creation** — group benchmark sessions into a named `Dataset` node
  for longitudinal analysis:
  `mas-lab graph dataset-create --help`
