# Neo4j Integration — `mas-library-kg`

Reference and example guide for writing, reading, and managing knowledge graphs in Neo4j using the `mas-library-kg` library.

---

## Table of Contents

1. [Conceptual Overview](#conceptual-overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Environment Variables](#environment-variables)
5. [`denormalize`](#denormalize)
6. [`push_kg_to_neo4j`](#push_kg_to_neo4j)
7. [`push_annotations_to_neo4j`](#push_annotations_to_neo4j)
8. [`fetch_kg_from_neo4j`](#fetch_kg_from_neo4j)
9. [`execute_merge`](#execute_merge)
10. [`build_merge_statements`](#build_merge_statements)
11. [Schema and Indexes](#schema-and-indexes)
12. [Property Serialization](#property-serialization)
13. [Constants](#constants)

---

## Conceptual Overview

### UNWIND-Batched Writes

All write operations use parameterized Cypher with `UNWIND` over lists of parameter maps, rather than one statement per node or edge. This collapses N round-trips into `ceil(N / batch_size)` round-trips and lets Neo4j batch-optimize the transaction plan.

```cypher
-- What the driver sends (conceptually):
UNWIND $rows AS row
MERGE (n:KGNode {id: row.id})
SET n += row.props
SET n:AgentCall
```

Because statements are parameterized, values are never interpolated into the Cypher string — eliminating injection risk and enabling driver-side query plan caching.

### The `KGNode` Secondary Label

Every node written by this library receives two labels:

- **Semantic label** — the node's `node_type` value (e.g., `AgentCall`, `State`, `Session`).
- **`KGNode`** — a shared secondary label applied to every node regardless of type.

The shared label enables cross-type queries without knowing in advance which semantic labels exist in the database:

```cypher
-- Find every node belonging to a session:
MATCH (n:KGNode {sessionId: "abc-123"}) RETURN n

-- Works even if you don't know the node types in advance.
```

It also lets the library create a single covering index on `KGNode.sessionId` that accelerates session-scoped queries for all node types simultaneously.

### Why `denormalize` Runs Before Push

Session-scoped fields (`sessionId`, `appId`, `source`, `block`) are not required to be present on individual nodes or edges in the source document. `denormalize` propagates these fields from the Session node outward to every element before any Cypher is generated. This ensures:

- Indexes on `sessionId` are useful from the moment data lands.
- Session-scoped deletes (`clear_session=True`) reliably find and remove all related nodes.
- Cross-session queries work uniformly without per-query type filtering.

### Property Serialization

Neo4j natively stores scalars, booleans, and lists of scalars. It does not store nested dicts or lists of dicts. Properties of those types are serialized to strings with a `__json__:` prefix before writing and deserialized automatically by `fetch_kg_from_neo4j`. See [Property Serialization](#property-serialization) for details.

---

## Installation

```bash
uv pip install "mas-library-kg[neo4j]"
```

This installs the base `mas-library-kg` package plus the `neo4j>=5.0` Python driver.

---

## Quick Start

```python
from mas.library.kg.neo4j import push_kg_to_neo4j, fetch_kg_from_neo4j

doc = {
    "nodes": [
        {"id": "sess-1", "node_type": "Session", "sessionId": "sess-1"},
        {"id": "agent-1", "node_type": "Agent", "name": "planner"},
        {"id": "call-1", "node_type": "AgentCall", "agent_id": "agent-1"},
    ],
    "edges": [
        {"source": "sess-1", "target": "call-1", "edge_type": "HAS_CALL"},
    ],
}

result = push_kg_to_neo4j(
    doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
    app_name="my-app",
)
print(result)
# {"rows": 4, "nodes": 3, "edges": 1, "uri": "bolt://localhost:7687", ...}

kg = fetch_kg_from_neo4j(
    session_id="sess-1",
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
)
print(len(kg["nodes"]))  # 3
```

---

## Environment Variables

The core push/fetch functions require explicit connection parameters. Step-function adapters and higher-level wrappers that sit on top of the core functions will fall back to these environment variables when explicit parameters are not provided.

| Variable        | Default                  | Description                       |
|-----------------|--------------------------|-----------------------------------|
| `NEO4J_URI`     | `bolt://localhost:7687`  | Bolt or neo4j+s connection URI    |
| `NEO4J_USER`    | `neo4j`                  | Database username                 |
| `NEO4J_PASSWORD` | *(none)*                | Database password                 |
| `NEO4J_DB_AGENT` | `neo4j`                 | Target database name              |

```bash
export NEO4J_URI="bolt://my-neo4j-host:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="s3cr3t"
export NEO4J_DB_AGENT="agents"
```

---

## `denormalize`

```python
from mas.library.kg.neo4j import denormalize

nodes, edges = denormalize(
    nodes,
    edges,
    *,
    app_name="",
    source="mas-lab",
    annotations=None,
)
```

Propagates session-scoped fields to every node and edge. Returns new lists — originals are never mutated. The function is idempotent: calling it twice on the same input produces the same result.

### Fields Written

| Field       | Value                                                                              |
|-------------|------------------------------------------------------------------------------------|
| `sessionId` | Resolved from the `Session` node's `sessionId` or `id`; falls back to any node's `run_id` |
| `appId`     | Value of `app_name`                                                                |
| `source`    | Value of `source` (default: `"mas-lab"`)                                           |
| `block`     | Determined by `node_type` — see Block Classification table below                  |

### Block Classification

| `block` value   | Node types                                                                 |
|-----------------|----------------------------------------------------------------------------|
| `"structural"`  | `Agent`, `CatalogTool`, `CatalogModel`, `CatalogSkill`                    |
| `"trajectory"`  | `State`, `Transition`                                                      |
| `"execution"`   | Everything else (default)                                                  |

### Precedence Rule

`annotations` are applied first, then `sessionId`, `appId`, and `source` always overwrite. This means custom annotations can set arbitrary properties but cannot silently override the three built-in session-tracking fields.

### Examples

**Example 1 — Basic propagation**

```python
from mas.library.kg.neo4j import denormalize

nodes = [
    {"id": "sess-1", "node_type": "Session", "sessionId": "sess-1"},
    {"id": "agent-1", "node_type": "Agent", "name": "planner"},
    {"id": "state-1", "node_type": "State", "label": "thinking"},
    {"id": "call-1", "node_type": "AgentCall"},
]
edges = [
    {"source": "agent-1", "target": "call-1", "edge_type": "MADE_CALL"},
]

out_nodes, out_edges = denormalize(nodes, edges, app_name="my-app", source="demo")

for n in out_nodes:
    print(n["node_type"], "->", n.get("block"), n.get("sessionId"), n.get("appId"))

# Session    -> execution   sess-1  my-app
# Agent      -> structural  sess-1  my-app
# State      -> trajectory  sess-1  my-app
# AgentCall  -> execution   sess-1  my-app

print(out_edges[0]["sessionId"])  # sess-1 — edges get it too
```

**Example 2 — Annotations applied before built-in fields**

```python
annotations = {
    "agent-1": {"team": "research", "sessionId": "IGNORED"},
    # "sessionId" in annotations is overwritten by the real session value
}

out_nodes, _ = denormalize(nodes, edges, app_name="app", annotations=annotations)

agent = next(n for n in out_nodes if n["id"] == "agent-1")
print(agent["team"])       # "research"  — annotation preserved
print(agent["sessionId"])  # "sess-1"    — built-in wins over annotation attempt
```

**Example 3 — Fallback to `run_id` when no Session node is present**

```python
nodes_no_session = [
    {"id": "call-1", "node_type": "AgentCall", "run_id": "run-xyz"},
]

out_nodes, _ = denormalize(nodes_no_session, [])
print(out_nodes[0]["sessionId"])  # "run-xyz"
```

---

## `push_kg_to_neo4j`

```python
from mas.library.kg.neo4j import push_kg_to_neo4j

result = push_kg_to_neo4j(
    doc,
    *,
    uri,
    username,
    password,
    database,
    batch_size=200,
    app_name="",
    source="mas-lab",
    annotations=None,
    clear_session=False,
    ensure_indexes=True,
    dry_run=False,
)
```

The primary high-level write function. Takes a `{"nodes": [...], "edges": [...]}` document, calls `denormalize`, then writes to Neo4j using UNWIND-batched parameterized Cypher MERGEs.

Every node receives two labels: its semantic `node_type` label plus `KGNode`.

### Parameters

| Parameter        | Type    | Default      | Description                                                                 |
|------------------|---------|--------------|-----------------------------------------------------------------------------|
| `doc`            | `dict`  | *(required)* | `{"nodes": [...], "edges": [...]}` document                                |
| `uri`            | `str`   | *(required)* | Neo4j Bolt or neo4j+s URI                                                  |
| `username`       | `str`   | *(required)* | Database username                                                           |
| `password`       | `str`   | *(required)* | Database password                                                           |
| `database`       | `str`   | *(required)* | Target database name                                                        |
| `batch_size`     | `int`   | `200`        | Nodes/edges per UNWIND batch                                                |
| `app_name`       | `str`   | `""`         | Populates `appId` on every element via `denormalize`                        |
| `source`         | `str`   | `"mas-lab"`  | Populates `source` on every element via `denormalize`                       |
| `annotations`    | `dict`  | `None`       | Per-node extra properties keyed by node `id`; applied before built-in fields |
| `clear_session`  | `bool`  | `False`      | If `True`, `DETACH DELETE` all nodes with matching `sessionId` before write |
| `ensure_indexes` | `bool`  | `True`       | If `True`, creates covering indexes on `KGNode` at startup                  |
| `dry_run`        | `bool`  | `False`      | If `True`, builds Cypher but does NOT connect or write; returns statements  |

### Return Value

```python
{
    "rows": int,      # total parameter rows processed
    "nodes": int,     # nodes written
    "edges": int,     # edges written
    "uri": str,       # connection URI used
    # additional driver metadata may be present
}
```

In `dry_run` mode the return value contains the generated Cypher statements instead of counts.

### Examples

**Example 1 — Basic write**

```python
from mas.library.kg.neo4j import push_kg_to_neo4j

doc = {
    "nodes": [
        {"id": "sess-abc", "node_type": "Session", "sessionId": "sess-abc"},
        {"id": "agent-1",  "node_type": "Agent",   "name": "summarizer"},
        {"id": "call-1",   "node_type": "AgentCall", "duration_ms": 420},
        {"id": "model-1",  "node_type": "CatalogModel", "model": "claude-3-5-sonnet"},
    ],
    "edges": [
        {"source": "sess-abc", "target": "agent-1", "edge_type": "DEFINES_AGENT"},
        {"source": "agent-1",  "target": "call-1",  "edge_type": "MADE_CALL"},
        {"source": "call-1",   "target": "model-1", "edge_type": "USED_MODEL"},
    ],
}

result = push_kg_to_neo4j(
    doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
    app_name="summarizer-service",
)
print(result)
# {"rows": 7, "nodes": 4, "edges": 3, "uri": "bolt://localhost:7687"}
```

**Example 2 — Dry run to inspect generated Cypher**

```python
result = push_kg_to_neo4j(
    doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="unused-in-dry-run",
    database="neo4j",
    dry_run=True,
)

for stmt in result["statements"]:
    print(stmt)
```

No connection is opened. Use this to audit what will be written or to capture statements for unit tests.

**Example 3 — Clear and repush a session**

Use `clear_session=True` when you need to overwrite a session that already exists in the database, for example after re-running a pipeline.

```python
result = push_kg_to_neo4j(
    doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
    app_name="summarizer-service",
    clear_session=True,   # DETACH DELETE existing nodes for this sessionId first
)
```

The delete runs as:

```cypher
MATCH (n {sessionId: $sid}) DETACH DELETE n
```

All relationships involving those nodes are removed before the new data is written.

**Example 4 — Per-node annotations**

```python
annotations = {
    "call-1": {"env": "production", "region": "us-east-1"},
    "agent-1": {"team": "nlp", "version": "2.3.0"},
}

result = push_kg_to_neo4j(
    doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
    annotations=annotations,
    app_name="summarizer-service",
)
```

Each node listed in `annotations` will have the extra properties merged in before the MERGE statement is executed. Built-in fields (`sessionId`, `appId`, `source`, `block`) still take precedence over any same-named annotation key.

**Example 5 — Large graph with custom batch size**

```python
result = push_kg_to_neo4j(
    large_doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
    batch_size=500,       # larger batches for high-throughput imports
    ensure_indexes=False, # indexes already exist; skip the check
)
```

---

## `push_annotations_to_neo4j`

```python
from mas.library.kg.neo4j import push_annotations_to_neo4j

result = push_annotations_to_neo4j(
    doc,
    *,
    uri,
    username,
    password,
    database,
    batch_size=200,
    app_name="",
    source="mas-lab",
    annotations=None,
    clear_session=False,
    ensure_indexes=True,
    dry_run=False,
)
```

Identical signature to `push_kg_to_neo4j` with one key difference: **`denormalize` is not called**. The nodes and edges in `doc` are written as-is.

### When to Use

Use `push_annotations_to_neo4j` when writing annotation nodes (such as `Metric`, `Evaluation`, `Tag`) that reference nodes from an already-pushed session. The referenced session nodes must already exist in Neo4j before calling this function, but dangling edge endpoints are allowed — the MERGE will create a relationship even if the target node does not yet exist.

Because `denormalize` is skipped, `sessionId` and other session fields must already be set on each node and edge in the document before calling this function, or must not be needed.

### Example — Pushing metrics after a session

```python
from mas.library.kg.neo4j import push_kg_to_neo4j, push_annotations_to_neo4j

# Step 1: push the main session graph
push_kg_to_neo4j(
    session_doc,
    uri=URI, username=USER, password=PASS, database=DB,
    app_name="eval-pipeline",
)

# Step 2: push metric annotations that reference session nodes
metrics_doc = {
    "nodes": [
        {
            "id": "metric-1",
            "node_type": "Metric",
            "sessionId": "sess-abc",      # must be pre-set
            "appId": "eval-pipeline",     # must be pre-set
            "source": "mas-lab",
            "block": "execution",
            "name": "latency_p99",
            "value": 340.5,
        },
    ],
    "edges": [
        {
            "source": "metric-1",
            "target": "sess-abc",         # this node already exists in Neo4j
            "edge_type": "MEASURES",
            "sessionId": "sess-abc",
        },
    ],
}

result = push_annotations_to_neo4j(
    metrics_doc,
    uri=URI, username=USER, password=PASS, database=DB,
)
print(result)
# {"rows": 2, "nodes": 1, "edges": 1, "uri": "..."}
```

---

## `fetch_kg_from_neo4j`

```python
from mas.library.kg.neo4j import fetch_kg_from_neo4j

kg = fetch_kg_from_neo4j(
    *,
    session_id=None,
    run_id=None,
    uri,
    username,
    password,
    database,
)
```

Retrieves a complete knowledge graph from Neo4j for a given session or run.

Exactly one of `session_id` or `run_id` must be provided. Providing both or neither raises an error.

### Parameters

| Parameter    | Type  | Description                                        |
|--------------|-------|----------------------------------------------------|
| `session_id` | `str` | Match nodes by `sessionId` property                |
| `run_id`     | `str` | Match nodes by `runId` property                    |
| `uri`        | `str` | Neo4j Bolt or neo4j+s URI                          |
| `username`   | `str` | Database username                                  |
| `password`   | `str` | Database password                                  |
| `database`   | `str` | Target database name                               |

### Return Shape

```python
{
    "nodes": [
        {
            "id": "call-1",
            "node_type": "AgentCall",   # resolved by finding semantic label (non-KGNode)
            "sessionId": "sess-abc",
            "appId": "my-app",
            "source": "mas-lab",
            "block": "execution",
            # any other properties stored on the node
            # dict/list properties are automatically deserialized from __json__: strings
        },
        ...
    ],
    "edges": [
        {
            "source": "agent-1",
            "target": "call-1",
            "edge_type": "MADE_CALL",
            "sessionId": "sess-abc",
            ...
        },
        ...
    ],
    "metadata": {
        "session_id": "sess-abc",
        "node_count": 4,
        "edge_count": 3,
        ...
    },
}
```

`node_type` is resolved by examining all labels on a node and selecting the one that is not `KGNode`. Dict and list properties stored as `__json__:...` strings are automatically deserialized back to their original Python types.

### Example

```python
from mas.library.kg.neo4j import fetch_kg_from_neo4j

kg = fetch_kg_from_neo4j(
    session_id="sess-abc",
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
)

print(kg["metadata"])
# {"session_id": "sess-abc", "node_count": 4, "edge_count": 3, ...}

for node in kg["nodes"]:
    print(node["node_type"], node["id"])
# Session    sess-abc
# Agent      agent-1
# AgentCall  call-1
# CatalogModel model-1

# Fetch by run_id instead:
kg2 = fetch_kg_from_neo4j(
    run_id="run-xyz",
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
)
```

---

## `execute_merge`

```python
from mas.library.kg.neo4j import execute_merge

result = execute_merge(
    nodes,
    edges,
    *,
    uri,
    username,
    password,
    database,
    batch_size=200,
)
```

Low-level write function. Takes pre-denormalized node and edge lists and writes them directly to Neo4j. Does not parse a `kg.jsonld`-style document dict, does not call `denormalize`.

### When to Use vs. `push_kg_to_neo4j`

| Situation | Use |
|---|---|
| Writing a complete `{"nodes": [...], "edges": [...]}` document | `push_kg_to_neo4j` |
| Nodes already have `sessionId`, `appId`, `source`, `block` set | `execute_merge` |
| Adapters in `mas-lab-graph` that manage denormalization themselves | `execute_merge` |
| Need `clear_session`, `ensure_indexes`, or `dry_run` support | `push_kg_to_neo4j` |

`execute_merge` is the inner workhorse that `push_kg_to_neo4j` calls after denormalization. Use it directly only when building custom pipeline adapters that need fine-grained control and have already handled field propagation.

### Example

```python
from mas.library.kg.neo4j import denormalize, execute_merge

# Custom pipeline: denormalize manually, then write
nodes = [...]
edges = [...]

d_nodes, d_edges = denormalize(nodes, edges, app_name="my-adapter")

result = execute_merge(
    d_nodes,
    d_edges,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="secret",
    database="neo4j",
    batch_size=100,
)
print(result)
# {"rows": ..., "nodes": ..., "edges": ...}
```

---

## `build_merge_statements`

```python
from mas.library.kg.neo4j import build_merge_statements

statements = build_merge_statements(nodes, edges)
```

Returns a list of display-oriented Cypher MERGE strings built from the provided node and edge lists. These strings are for human inspection only — they are not used for actual writes and do not contain parameter bindings.

### When to Use

- Capturing expected Cypher output in unit tests.
- Printing what would be written before committing to a push.
- Debugging schema issues by reading the generated patterns.
- Combining with `dry_run=True` in `push_kg_to_neo4j` for full visibility.

### Example — Dry-run inspection pipeline

```python
from mas.library.kg.neo4j import denormalize, build_merge_statements, push_kg_to_neo4j

nodes = [
    {"id": "sess-1",  "node_type": "Session",   "sessionId": "sess-1"},
    {"id": "agent-1", "node_type": "Agent",      "name": "planner"},
    {"id": "call-1",  "node_type": "AgentCall",  "tokens": 512},
]
edges = [
    {"source": "agent-1", "target": "call-1", "edge_type": "MADE_CALL"},
]

# Step 1: denormalize to populate session fields
d_nodes, d_edges = denormalize(nodes, edges, app_name="demo")

# Step 2: inspect the Cypher that would be sent
for stmt in build_merge_statements(d_nodes, d_edges):
    print(stmt)
# MERGE (n:KGNode {id: "sess-1"}) SET n += {...} SET n:Session
# MERGE (n:KGNode {id: "agent-1"}) SET n += {...} SET n:Agent
# MERGE (n:KGNode {id: "call-1"}) SET n += {...} SET n:AgentCall
# MATCH (a:KGNode {id: "agent-1"}), (b:KGNode {id: "call-1"})
#   MERGE (a)-[r:MADE_CALL]->(b) SET r += {...}

# Step 3: optionally do a full dry run through push_kg_to_neo4j
result = push_kg_to_neo4j(
    {"nodes": nodes, "edges": edges},
    uri="bolt://localhost:7687",
    username="neo4j",
    password="unused",
    database="neo4j",
    app_name="demo",
    dry_run=True,
)
print(result["statements"])
```

### Example — Unit test assertion

```python
def test_merge_statements_include_kgnode_label():
    nodes = [{"id": "n1", "node_type": "AgentCall", "sessionId": "s1"}]
    stmts = build_merge_statements(nodes, [])
    assert any("KGNode" in s for s in stmts)
    assert any("AgentCall" in s for s in stmts)
```

---

## Schema and Indexes

### Indexes Created by `ensure_indexes=True`

When `push_kg_to_neo4j` is called with `ensure_indexes=True` (the default), the following indexes are created if they do not already exist:

| Index name                  | Label    | Property    | Purpose                                          |
|-----------------------------|----------|-------------|--------------------------------------------------|
| `kgnode_session_id_idx`     | `KGNode` | `sessionId` | Fast session-scoped lookups and deletes          |
| `kgnode_run_id_idx`         | `KGNode` | `runId`     | Lookup by pipeline run identifier                |
| `kgnode_id_idx`             | `KGNode` | `id`        | Node identity lookups for MERGE and relationship resolution |

All three are composite range indexes on the `KGNode` label, which means they cover every node regardless of semantic type.

### Example Queries

**All nodes in a session:**

```cypher
MATCH (n:KGNode {sessionId: "sess-abc"})
RETURN n.id, labels(n), n.block
ORDER BY n.block
```

**All Agent nodes across sessions for an app:**

```cypher
MATCH (n:Agent:KGNode {appId: "summarizer-service"})
RETURN n.name, n.sessionId
```

**Execution-block nodes only:**

```cypher
MATCH (n:KGNode {sessionId: "sess-abc", block: "execution"})
RETURN n
```

**Find all calls made by a specific agent:**

```cypher
MATCH (a:Agent:KGNode {sessionId: "sess-abc"})-[:MADE_CALL]->(c:AgentCall:KGNode)
RETURN a.name, c.id, c.duration_ms
```

**Delete a session and all its nodes:**

```cypher
MATCH (n:KGNode {sessionId: "sess-abc"})
DETACH DELETE n
```

**Inspect index usage:**

```cypher
EXPLAIN MATCH (n:KGNode {sessionId: "sess-abc"}) RETURN n
```

### Manually Creating Indexes

If you set `ensure_indexes=False` and want to create indexes manually:

```cypher
CREATE INDEX kgnode_session_id_idx IF NOT EXISTS
FOR (n:KGNode) ON (n.sessionId);

CREATE INDEX kgnode_run_id_idx IF NOT EXISTS
FOR (n:KGNode) ON (n.runId);

CREATE INDEX kgnode_id_idx IF NOT EXISTS
FOR (n:KGNode) ON (n.id);
```

---

## Property Serialization

Neo4j stores scalars, booleans, and flat lists of scalars natively. Nested dicts and lists of dicts are not natively supported.

`mas-library-kg` handles this transparently using a `__json__:` prefix convention:

| Python type   | Stored in Neo4j as                      |
|---------------|-----------------------------------------|
| `str`         | `"hello"`                               |
| `int`/`float` | `42` / `3.14`                           |
| `bool`        | `true` / `false`                        |
| `list[scalar]`| `["a", "b", "c"]`                       |
| `dict`        | `"__json__:{\"key\": \"value\"}"`       |
| `list[dict]`  | `"__json__:[{\"a\": 1}, {\"b\": 2}]"`  |

### Rules

- Serialization happens automatically before write; deserialization happens automatically on `fetch_kg_from_neo4j`.
- You never need to pre-serialize or post-deserialize manually when using the high-level API.
- If you read nodes using raw Cypher (not through `fetch_kg_from_neo4j`), you will see the `__json__:...` string and must deserialize it yourself:

```python
import json

raw_value = node_props.get("tool_calls")
if isinstance(raw_value, str) and raw_value.startswith("__json__:"):
    tool_calls = json.loads(raw_value[len("__json__:"):])
```

---

## Constants

```python
from mas.library.kg.neo4j import KGNODE_LABEL

print(KGNODE_LABEL)  # "KGNode"
```

`KGNODE_LABEL` is the string `"KGNode"` — the shared secondary label applied to every node. Import it when constructing Cypher queries programmatically to avoid hardcoding the string.

```python
from mas.library.kg.neo4j import KGNODE_LABEL

cypher = f"MATCH (n:{KGNODE_LABEL} {{sessionId: $sid}}) RETURN n"
```
