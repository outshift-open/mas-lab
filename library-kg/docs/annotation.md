# KG Annotation — Reference and Examples

`mas-library-kg` ships a generic mechanism for attaching computed data to
knowledge-graph nodes without touching the original document.  This guide
covers the concept, the full API, idempotency guarantees, worked examples,
and the integration pattern for pushing annotations to Neo4j.

---

## Contents

1. [Concept](#concept)
2. [API Reference](#api-reference)
3. [Stable IDs and Idempotency](#stable-ids-and-idempotency)
4. [Examples](#examples)
   - [Example 1 — Embed State nodes via OpenAI](#example-1--embed-state-nodes-via-openai)
   - [Example 2 — Score LLMCall nodes](#example-2--score-llmcall-nodes)
   - [Example 3 — Classify ToolCall nodes, skipping empties](#example-3--classify-toolcall-nodes-skipping-empties)
   - [Example 4 — Pure computed annotation without a model](#example-4--pure-computed-annotation-without-a-model)
5. [Pushing Annotations to Neo4j](#pushing-annotations-to-neo4j)
6. [Custom annotation_node_type and id_prefix](#custom-annotation_node_type-and-id_prefix)
7. [Deprecation: embed_state_nodes](#deprecation-embed_state_nodes)

---

## Concept

A KG document (`kg.jsonld`) is a plain dict with two top-level lists:

```python
{
    "nodes": [...],   # graph nodes, each with "id" and "node_type"
    "edges": [...],   # directed edges, each with "from_id", "to_id", "edge_type"
    # ... other metadata fields preserved as-is
}
```

**Annotation** means attaching a computed value — an embedding vector, a
quality score, a label, a classification — to one or more existing nodes
**without mutating the original document**.  The result is a new document
that contains the original nodes and edges plus additional annotation nodes
and the edges that link them to their sources.

Key properties of the annotation model:

- **Immutability.** The input `doc` is never modified.  `annotate_kg_nodes`
  always returns a new dict.  The original can be passed to multiple
  annotation calls safely.

- **Idempotency.** Annotation node IDs are deterministic: they are derived
  from the source node's `id` and the `edge_name` only, using a SHA-256
  hash.  Re-running the same annotation over the same document produces
  identical IDs, so merging the result into Neo4j with `MERGE` is safe —
  no duplicates accumulate.

- **Separation of concerns.** `annotate_kg_nodes` owns graph structure
  (node creation, edge wiring, ID generation).  The caller owns the
  computation (calling an embedding API, running a scorer, applying a
  regex).  The boundary is the `value_fn` callable.

### Typical use cases

| Use case | node_type | edge_name | annotation fields |
|---|---|---|---|
| Semantic embeddings | `State` | `hasEmbedding` | `vector`, `model`, `dimensions` |
| Response quality score | `LLMCall` | `hasScore` | `score`, `scorer`, `rationale` |
| Tool output classification | `ToolCall` | `hasLabel` | `label`, `confidence` |
| Toxicity / sentiment | `LLMCall` | `hasToxicity` | `toxicity`, `sentiment` |
| Length bucketing | `LLMCall` | `hasLengthBucket` | `bucket`, `char_count` |
| Custom metrics | any | any valid identifier | arbitrary fields |

---

## API Reference

### `annotate_kg_nodes`

```python
from mas.library.kg import annotate_kg_nodes
# or
from mas.library.kg import annotate_kg_nodes
# or
from mas.library.kg.core.annotate import annotate_kg_nodes
```

```
annotate_kg_nodes(
    doc,
    *,
    node_type,
    edge_name,
    value_fn,
    annotation_node_type="Annotation",
    id_prefix="urn:mas:annotation:",
) -> dict
```

**Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `doc` | `dict` | yes | KG document: `{"nodes": [...], "edges": [...], ...}` |
| `node_type` | `str` | yes | Only process nodes where `node["node_type"] == node_type` |
| `edge_name` | `str` | yes | `edge_type` on the new edges (e.g. `"hasEmbedding"`) |
| `value_fn` | `Callable[[dict], dict \| None]` | yes | Called once per matching node.  Return a dict of fields to store on the annotation node, or `None` to skip this node. |
| `annotation_node_type` | `str` | no | `node_type` written on each new annotation node.  Default: `"Annotation"` |
| `id_prefix` | `str` | no | URI prefix for generated annotation IDs.  Default: `"urn:mas:annotation:"` |

**Return value**

A new `dict` with the same structure as `doc` plus the annotation nodes and
edges appended to `"nodes"` and `"edges"`.  All other top-level keys from
`doc` (e.g. `"metadata"`, `"run_id"`) are preserved unchanged.

If `value_fn` returns `None` for every matching node, or if there are no
matching nodes, the **original `doc` object is returned unchanged** (not a
copy).

**Raises**

- `TypeError` — if `value_fn` returns something other than `dict` or `None`.

**Annotation node structure**

Each new node has the following guaranteed fields, plus whatever `value_fn`
returned:

```python
{
    "id":             "<id_prefix><16-hex-chars>",   # stable, deterministic
    "node_type":      annotation_node_type,
    "source_node_id": "<id of the source node>",
    # ... all fields from value_fn return value
}
```

**Edge structure**

```python
{
    "from_id":  "<source node id>",
    "to_id":    "<annotation node id>",
    "edge_type": edge_name,
}
```

### `run_annotate` (step wrapper)

```python
from mas.library.kg.steps.annotate import run_annotate
```

A convenience wrapper that reads a `kg.jsonld` file, calls `annotate_kg_nodes`,
and writes the result back to disk.

```python
result = run_annotate(
    kg_path,
    value_fn,
    node_type="State",
    edge_name="hasEmbedding",
    annotation_node_type="Annotation",
    output_path=None,   # defaults to overwriting kg_path
    dry_run=False,
)
# result = {"kg_path": "/path/to/output.json", "annotated_count": 12}
```

---

## Stable IDs and Idempotency

Annotation node IDs are computed as follows:

```python
import hashlib, json

content_hash = hashlib.sha256(
    json.dumps({"source": source_id, "edge": edge_name}, sort_keys=True).encode()
).hexdigest()[:16]

annotation_id = f"{id_prefix}{content_hash}"
```

The inputs are **the source node's `id`** and **the `edge_name`**.  The
`value_fn` output does not affect the ID.

Consequences:

1. Running the same annotation twice on the same document produces the same
   annotation node IDs.  Pushing to Neo4j with `MERGE` is safe — the
   second push updates properties rather than creating a duplicate.

2. Different `edge_name` values produce different IDs for the same source
   node, so a node can have independent `hasEmbedding`, `hasScore`, and
   `hasLabel` annotations with no collision.

3. The `id_prefix` is part of the ID string but is not hashed.  Changing the
   prefix changes the ID, which breaks idempotency across prefix changes.
   Pick a prefix and keep it stable for the lifetime of the dataset.

4. If a source node has no `"id"` field, `annotate_kg_nodes` falls back to
   `uuid.uuid4()`, which is non-deterministic.  Nodes without IDs will not
   be idempotent; ensure source nodes always carry an `"id"`.

---

## Examples

### Example 1 — Embed State nodes via OpenAI

This is the canonical embedding use case.  Each `State` node represents a
snapshot of agent working memory.  Embedding the `content` field enables
semantic search and trajectory clustering.

```python
import json
from pathlib import Path

import openai
from mas.library.kg import annotate_kg_nodes

client = openai.OpenAI()  # reads OPENAI_API_KEY from env


def embed_fn(node: dict) -> dict | None:
    """Embed the content field; skip nodes with no text."""
    content = (node.get("content") or "").strip()
    if not content:
        return None
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=[content],
    )
    vector = resp.data[0].embedding
    return {
        "vector": vector,
        "model": "text-embedding-3-small",
        "dimensions": len(vector),
    }


kg_path = Path("output/session-abc/kg.jsonld")
doc = json.loads(kg_path.read_text())

enriched = annotate_kg_nodes(
    doc,
    node_type="State",
    edge_name="hasEmbedding",
    value_fn=embed_fn,
    annotation_node_type="StateEmbedding",
    id_prefix="urn:mas:emb:",
)

kg_path.write_text(json.dumps(enriched, indent=2))

# Count what was added
original_count = len(doc["nodes"])
added = len(enriched["nodes"]) - original_count
print(f"Added {added} StateEmbedding nodes")
```

**Result shape** — each new node looks like:

```json
{
  "id": "urn:mas:emb:3f8a1c9e72b04d51",
  "node_type": "StateEmbedding",
  "source_node_id": "state-001",
  "vector": [0.023, -0.114, ...],
  "model": "text-embedding-3-small",
  "dimensions": 1536
}
```

**Tip:** For large sessions, batch the embedding calls rather than calling
the API once per node.  Collect all content strings first, call the API once
in `value_fn` via a pre-built lookup table:

```python
# Pre-build a {node_id: vector} map before calling annotate_kg_nodes
state_nodes = [n for n in doc["nodes"] if n.get("node_type") == "State"]
contents = [(n["id"], (n.get("content") or "").strip()) for n in state_nodes]
non_empty = [(nid, c) for nid, c in contents if c]

if non_empty:
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=[c for _, c in non_empty],
    )
    vector_map = {nid: resp.data[i].embedding for i, (nid, _) in enumerate(non_empty)}
else:
    vector_map = {}


def embed_fn(node: dict) -> dict | None:
    vec = vector_map.get(node.get("id") or "")
    if vec is None:
        return None
    return {"vector": vec, "model": "text-embedding-3-small", "dimensions": len(vec)}


enriched = annotate_kg_nodes(doc, node_type="State", edge_name="hasEmbedding",
                              value_fn=embed_fn, annotation_node_type="StateEmbedding")
```

---

### Example 2 — Score LLMCall nodes

Attach a quality score to each LLM call.  Here `value_fn` uses a mocked
scorer; replace the body with any scoring logic (a rubric LLM call, a
heuristic, a regex-based check, etc.).

```python
import re
from mas.library.kg import annotate_kg_nodes


def score_llm_call(node: dict) -> dict | None:
    """
    Score an LLMCall node based on its output.

    Returns None to skip nodes with no output (e.g. errored calls).
    """
    output = (node.get("output") or node.get("response") or "").strip()
    if not output:
        return None  # skip — no response to score

    # --- replace this block with your actual scorer ---
    word_count = len(output.split())
    has_reasoning = bool(re.search(r"\bbecause\b|\btherefore\b|\bthus\b", output, re.I))
    score = min(1.0, word_count / 200.0)
    if has_reasoning:
        score = min(1.0, score + 0.15)
    # --------------------------------------------------

    return {
        "score": round(score, 4),
        "scorer": "heuristic-v1",
        "word_count": word_count,
        "has_reasoning": has_reasoning,
    }


enriched = annotate_kg_nodes(
    doc,
    node_type="LLMCall",
    edge_name="hasScore",
    value_fn=score_llm_call,
    annotation_node_type="QualityScore",
    id_prefix="urn:mas:score:",
)
```

**Result shape:**

```json
{
  "id": "urn:mas:score:a17f3b8c9d012e44",
  "node_type": "QualityScore",
  "source_node_id": "llmcall-007",
  "score": 0.8700,
  "scorer": "heuristic-v1",
  "word_count": 154,
  "has_reasoning": true
}
```

---

### Example 3 — Classify ToolCall nodes, skipping empties

Return `None` from `value_fn` to skip any node that does not warrant an
annotation.  Here, ToolCall nodes that produced no output (e.g. a failed
tool invocation) are skipped entirely — no annotation node is created for
them.

```python
from mas.library.kg import annotate_kg_nodes

# A simple rule-based classifier for tool output categories
TOOL_CATEGORIES = {
    "search":    ["results", "found", "items"],
    "compute":   ["result", "value", "calculated"],
    "retrieval": ["document", "file", "content"],
    "error":     ["error", "failed", "exception", "traceback"],
}


def classify_tool_call(node: dict) -> dict | None:
    """
    Classify a ToolCall by its output.  Skip calls with no output.
    """
    output = (node.get("output") or "").strip()
    if not output:
        return None  # no output — skip, do not annotate

    output_lower = output.lower()
    matched_label = "unknown"
    best_score = 0

    for label, keywords in TOOL_CATEGORIES.items():
        hits = sum(1 for kw in keywords if kw in output_lower)
        if hits > best_score:
            best_score = hits
            matched_label = label

    return {
        "label": matched_label,
        "confidence": min(1.0, best_score / 3.0),
        "classifier": "keyword-v1",
    }


enriched = annotate_kg_nodes(
    doc,
    node_type="ToolCall",
    edge_name="hasLabel",
    value_fn=classify_tool_call,
    annotation_node_type="ToolCallLabel",
    id_prefix="urn:mas:label:",
)

# How many ToolCall nodes were annotated vs skipped?
tool_calls = [n for n in doc["nodes"] if n.get("node_type") == "ToolCall"]
labels_added = len(enriched["nodes"]) - len(doc["nodes"])
print(f"{labels_added} of {len(tool_calls)} ToolCall nodes classified")
```

**When `value_fn` returns `None`:**

- No annotation node is created.
- No edge is created.
- The source node is left untouched in the output document.
- The total node and edge counts increase only by the number of non-None
  returns.

---

### Example 4 — Pure computed annotation without a model

Not every annotation requires a model.  This example adds a
`response_length_bucket` annotation to each `LLMCall` node based solely on
the character count of its response.  No external API is involved — the
`value_fn` is pure Python.

```python
from mas.library.kg import annotate_kg_nodes


def length_bucket(node: dict) -> dict | None:
    """Bucket LLMCall responses by output length."""
    output = (node.get("output") or node.get("response") or "").strip()
    char_count = len(output)

    if char_count == 0:
        return None  # no response; skip

    if char_count < 100:
        bucket = "xs"
    elif char_count < 500:
        bucket = "sm"
    elif char_count < 2000:
        bucket = "md"
    elif char_count < 8000:
        bucket = "lg"
    else:
        bucket = "xl"

    return {
        "bucket": bucket,
        "char_count": char_count,
    }


enriched = annotate_kg_nodes(
    doc,
    node_type="LLMCall",
    edge_name="hasLengthBucket",
    value_fn=length_bucket,
    annotation_node_type="LengthBucket",
    id_prefix="urn:mas:len:",
)
```

**Result shape:**

```json
{
  "id": "urn:mas:len:c92d4f1a8e3b0765",
  "node_type": "LengthBucket",
  "source_node_id": "llmcall-012",
  "bucket": "md",
  "char_count": 743
}
```

Pure computed annotations are cheap to re-generate and useful as pre-filters
before expensive model calls — for example, skip embedding nodes in the `xs`
bucket because they carry too little signal.

---

## Pushing Annotations to Neo4j

### Why `push_annotations_to_neo4j` instead of `push_kg_to_neo4j`

`push_kg_to_neo4j` assumes the document is a self-contained session graph.
Before writing, it runs a *denormalize* step that stamps every node and edge
with session-scoped attributes (`sessionId`, `appId`, `source`, `block`).

Annotation documents are different: their edges reference **existing nodes**
that are already in Neo4j (the original session graph nodes), but those
source nodes are NOT present in the annotation document.  Denormalizing them
would fail or produce misleading results.

`push_annotations_to_neo4j` calls `push_kg_to_neo4j` with
`skip_denormalize=True` and uses `MERGE` semantics, so:

- Annotation nodes are upserted safely (idempotent re-runs).
- Edge `MATCH` statements find the referenced source nodes in Neo4j.
- If a source node does not exist yet, that edge is silently skipped
  (Neo4j `MATCH` finds nothing; no error is raised).

### Full pattern

```python
import json
from pathlib import Path

from mas.library.kg import annotate_kg_nodes
from mas.library.kg.neo4j.push import push_annotations_to_neo4j


# 1. Load the session KG document
doc = json.loads(Path("output/session-abc/kg.jsonld").read_text())


# 2. Build a value_fn (inline or imported)
def embed_fn(node: dict) -> dict | None:
    content = (node.get("content") or "").strip()
    if not content:
        return None
    # ... call your embedding API here ...
    return {"vector": [0.0] * 1536, "model": "text-embedding-3-small", "dimensions": 1536}


# 3. Annotate — returns a new doc; original is unchanged
annotations_doc = annotate_kg_nodes(
    doc,
    node_type="State",
    edge_name="hasEmbedding",
    value_fn=embed_fn,
    annotation_node_type="StateEmbedding",
    id_prefix="urn:mas:emb:",
)

# 4. Extract only the new nodes and edges (optional — push_annotations_to_neo4j
#    accepts the full enriched doc and ignores the original session nodes because
#    skip_denormalize=True, but they do no harm if present)
result = push_annotations_to_neo4j(
    annotations_doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="password",
    database="neo4j",
)

print(result)
# {"nodes_pushed": 42, "edges_pushed": 42, "dry_run": False, "rows": 84}
```

### Dry-run mode

Pass `dry_run=True` to inspect the Cypher without writing:

```python
result = push_annotations_to_neo4j(
    annotations_doc,
    uri="bolt://localhost:7687",
    username="neo4j",
    password="neo4j",
    database="neo4j",
    dry_run=True,
)
# result["statements"] contains the Cypher strings
for stmt in result.get("statements", []):
    print(stmt)
```

### Re-running annotations (idempotency in practice)

Because annotation IDs are deterministic, calling `push_annotations_to_neo4j`
a second time with the same inputs is safe.  Neo4j `MERGE` finds each
annotation node by its `id` property and updates its properties in place
rather than creating a duplicate.  This makes it straightforward to re-run
annotation pipelines after changing the model or scorer: the node ID stays
the same, and the properties are overwritten.

---

## Custom `annotation_node_type` and `id_prefix`

### `annotation_node_type`

The `annotation_node_type` parameter controls the `node_type` field written on
every new annotation node.  It also becomes a Neo4j label when pushed via
`push_annotations_to_neo4j`.

Recommendations:

- Use `PascalCase` to match the rest of the KG ontology node types.
- Be specific: `StateEmbedding` is preferable to `Annotation` when all
  annotations in a document are embeddings of State nodes.
- Use the default `"Annotation"` only for ad-hoc or mixed-purpose documents
  where you do not need to query by annotation type.
- Avoid reusing the same `annotation_node_type` across semantically different
  annotations (e.g. do not use `"LLMAnnotation"` for both a score and a label).

Common patterns:

```python
# Semantic embeddings
annotation_node_type="StateEmbedding"

# Scalar scores
annotation_node_type="QualityScore"

# Categorical labels
annotation_node_type="ToolCallLabel"

# Toxicity / safety signals
annotation_node_type="SafetyAnnotation"

# Pure computed metrics
annotation_node_type="LengthBucket"
```

### `id_prefix`

The `id_prefix` is prepended to the 16-character hex hash to form the full
annotation node ID.

Recommendations:

- Use URN-style prefixes to avoid collisions: `"urn:mas:emb:"`,
  `"urn:mas:score:"`, `"urn:mas:label:"`.
- Include a version token if you anticipate changing the hash inputs:
  `"urn:mas:emb:v2:"`.
- Keep the prefix stable for the lifetime of a dataset.  Changing it
  changes all IDs, which causes Neo4j `MERGE` to create new nodes instead
  of updating existing ones.
- The prefix is stored as part of the `id` field in Neo4j, so it doubles
  as a human-readable namespace for debugging (`MATCH (n) WHERE n.id STARTS
  WITH 'urn:mas:emb:' RETURN n`).

---

## Deprecation: `embed_state_nodes`

`embed_state_nodes` from `mas.library.kg.embeddings` is a deprecated shim.
It accepts a batch embed function (one that takes a list of strings and
returns a list of vectors) and wires it into `annotate_kg_nodes` internally.

```python
# Deprecated — raises DeprecationWarning
from mas.library.kg.embeddings import embed_state_nodes
enriched = embed_state_nodes(doc, embed_fn=lambda texts: [...])
```

It is exactly equivalent to:

```python
from mas.library.kg import annotate_kg_nodes

def value_fn(node):
    content = (node.get("content") or "").strip()
    if not content:
        return None
    vec = vector_map.get(node.get("id") or "")
    if vec is None:
        return None
    return {"vector": vec, "model": model, "dimensions": len(vec)}

enriched = annotate_kg_nodes(
    doc,
    node_type="State",
    edge_name="hasEmbedding",
    value_fn=value_fn,
    annotation_node_type="StateEmbedding",
)
```

The shim will be removed in a future release.  Migrate to `annotate_kg_nodes`
directly.  The main advantages of migrating:

- Full control over what fields are stored on the annotation node.
- Support for any node type, not just `State`.
- Support for any edge name, not just `hasEmbedding`.
- No need to batch-produce a vector map manually; `value_fn` can call any
  API per-node or consume a pre-built lookup.
