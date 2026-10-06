<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 8 — Building a knowledge graph from OTel and native events

> **Packages:** `mas-library-kg` (native→KG is first-party; OTel→KG reuses
> OXP's own `norm` package), `mas-library-telemetry` (span files from
> [Tutorial 7](../07-telemetry/))
> **Prerequisite:** [Tutorial 7](../07-telemetry/).
> **Example traces:** [`library-kg/examples/qa-agent/`](../../../library-kg/examples/qa-agent/)
> (same layout as `examples/trip-planner/`)

Tutorial 7 gave you two exports of the same run: native `events.jsonl` and
OTel spans. Neither is a **knowledge graph** — both are flat, ordered logs.
To ask graph questions ("which tools did this agent call", "what's the call
tree") you need to normalize one of those exports into typed nodes and
edges.

For OTel spans, that normalization already exists: OXP's own `norm` package
turns OTel spans into `oxp_ontology.models.*` nodes and edges — the same
ontology the Observe and eXplain Platform itself uses. There's no reason to
reimplement it, so `mas-library-kg`'s OTel path is a thin wrapper around
`norm.normalize()`.

For native events, no such package exists — nothing outside MAS Lab
understands `events.jsonl` — so the native path is first-party: this
library walks native events itself and builds the same `oxp_ontology.models.*`
graph directly, with no OTel and no `norm` dependency in the loop.

This tutorial builds both graphs from the qa-agent example, serializes them,
and proves they describe the same run.

| # | What you do |
| --- | --- |
| 1 | OTel → KG, reusing OXP's `norm.normalize()` |
| 2 | Native → KG (first-party, no OTel) |
| 3 | Serialize: `kg.jsonld` vs Neo4j / OXP infra |
| 4 | Equivalence: native → OTel → KG vs native → KG |
| 5 | Validate against the ontology (`mas-lab kg validate`, structural + SHACL) |
| 6 | Realtime: normalize and push the graph while the run is still happening |

```bash
uv pip install -e "library-kg[verify]"          # native → KG
uv pip install -e "library-kg[norm,verify]"     # OTel → KG (OXP wrap)
uv pip install -e "library-telemetry[convert]"  # if you still need replay
```

```bash
pytest tests/tutorials/test_tutorial_08.py tests/tutorials/test_scenario_commands.py -k tuto-08
```

`mas-lab kg normalize` and `mas-lab kg neo4j-push` are **CLI shortcuts** for
the same `normalize_events` / `normalize_otel` / `neo4j_push` pipeline steps
used by `kg:pipelines/native-to-kg.yaml` and
`kg:pipelines/native-to-neo4j.yaml`. Native→KG is first-party. OTel→KG wraps
`norm.normalize()` — the exact same normalizer OXP's own ingestion uses, so
a graph built here matches one the platform would have built from the same
spans.

Serialization is the last hop:

| Sink | What you pass | Who chooses it |
| --- | --- | --- |
| JSON-LD file | a path (`-o`, `output_dir`, `kg.jsonld`) | you |
| Neo4j | an infra manifest (`--infra`, `kind: Neo4j`) | the manifest |
| Env shortcut | `$NEO4J_URI` | replaces a one-target YAML |

A built graph can carry more than one category — `structure`/`execution`/
`trajectory` by default; `provenance`, `governance`, and `infrastructure` are
off. Tune them on the CLI (`--include-governance`, `--include-provenance`, …)
or on the pipeline step (`include_governance: true`) — the same categories
Tutorial 7 uses for the OTel export.

---

## 1 — OTel → KG, reusing OXP's `norm`

`mas-library-kg` does **not** reimplement OXP's normalizer. `normalize_otel`
wraps `norm.normalize()`, so the result is the same shape of graph
(`oxp_ontology.models.*`) the platform itself would produce from the same
spans.

```bash
python - <<'PY'
from pathlib import Path
from mas.library.kg.steps.normalize_otel import run_normalize_otel
out = Path("/tmp/t8-otel-kg")
art = run_normalize_otel(
    Path("library-kg/examples/qa-agent/otel_spans.jsonl"),
    run_id="t8-otel",
    output_dir=out,
)
print(art.node_count, "nodes", art.edge_count, "edges →", out / "kg.jsonld")
PY
```

`mas-lab kg normalize --otel spans.jsonl -o kg.jsonld` is the file-sink
shortcut. Pipeline: `kg:pipelines/otel-to-kg.yaml`.

Shipped graph: [`library-kg/examples/qa-agent/kg-otel.jsonld`](../../../library-kg/examples/qa-agent/kg-otel.jsonld).

---

## 2 — Native → KG

The other half of the problem: native events have no normalizer to call.
This path walks them directly into the same ontology models — no OTel and
no `norm` extra. Unmapped native kinds are skipped with a warning (not an
error).

```bash
python - <<'PY'
from pathlib import Path
from mas.library.kg.steps.normalize import run_normalize
out = Path("/tmp/t8-native-kg")
art = run_normalize(
    Path("library-kg/examples/qa-agent/events.jsonl"),
    run_id="t8-native",
    output_dir=out,
)
print(art.node_count, "nodes", art.edge_count, "edges →", out / "kg.jsonld")
PY
```

`mas-lab kg normalize events.jsonl -o kg.jsonld` is the file-sink shortcut
(`--include-governance` opts the governance category in). Pipeline:
`kg:pipelines/native-to-kg.yaml`.

Shipped graph: [`library-kg/examples/qa-agent/kg-native.jsonld`](../../../library-kg/examples/qa-agent/kg-native.jsonld).

Library-kg tutorial with Neo4j round-trip:
[library-kg/docs/tutorial.md](../../../library-kg/docs/tutorial.md).

---

## 3 — Serialization

| Artifact | File (always) | Service (infra manifest) | Env shortcut |
| --- | --- | --- | --- |
| Knowledge graph | `kg.json` / `kg.jsonld` | `Neo4j` → `library-kg/infra/local-neo4j.yaml` | `$NEO4J_URI` |

```bash
docker compose -f library-kg/docker/compose.yaml up -d
export NEO4J_URI=bolt://localhost:7687
```

The Observe-and-Explain Platform stack (norm worker, API, UI, RabbitMQ) is
not a single published image. Use
[backend/docker-compose.yml](https://github.com/outshift-open/observe-and-explain-platform/blob/main/backend/docker-compose.yml)
in that OSS repo when you want the product UI. In-process `norm.normalize()`
for §1 does not require it.

Push KG after Neo4j is up (`--dry-run` prints Cypher and does not connect;
`neo4j-push` is an alias of `push`):

```bash
mas-lab kg neo4j-push library-kg/examples/qa-agent/kg-native.jsonld --dry-run
mas-lab kg neo4j-push library-kg/examples/qa-agent/kg-native.jsonld \
  --infra library-kg/infra/local-neo4j.yaml --dry-run
```

See `library-kg/docker/README.md`. If your team runs a shared Neo4j instead
of a local one, write an infra manifest for it (same shape as
`local-neo4j.yaml`, with that instance's URI) and point `--infra` at that
file instead.

---

## 4 — Equivalence: OTel→KG vs native→KG

If both paths target the same ontology, they should agree on the same run.
Default layers and complete layers (all observe-sdk extensions) are both
checked. Comparison is the canonical call-tree modulo order, not hashed ids,
since live/replay and native mint ids differently.

```bash
cd library-kg
python -m pytest tests/kg/test_native_otel_norm_equivalence.py -q
```

Requires `mas-library-kg[norm]` and `mas-library-telemetry[convert]`.

---

## 5 — Validate against the ontology (structural + SHACL)

Building a graph that merely looks right isn't enough — it should conform
to the published OXP ontology: known vocabulary, blocks, and layers, plus
the `mas-shapes.ttl` SHACL shapes shipped in `oxp-ontology`. `mas-lab kg
validate` checks both.

```bash
uv pip install -e "library-kg[validation]"   # rdflib + pyshacl
mas-lab kg validate library-kg/examples/qa-agent/kg-native.jsonld
mas-lab kg validate library-kg/examples/qa-agent/kg-otel.jsonld
```

Default checks include `shacl`. A missing `[validation]` extra skips SHACL
instead of passing it. Vocabulary checks (`unknown_*`, `block`, `layer`,
orphans) pass on the qa-agent fixtures. Remaining SHACL rows are mostly
`sh:Warning` (LLM token/provider fields, `hasToolCall` on an agent with no
tools) plus a few `belongsToMAS` / `belongsToMASCall` cardinality hits on
this short capture. Run validate on every new `kg.jsonld`.

---

## 6 — Realtime: normalize and push the graph while the run is still happening

Tutorial 7 §6 showed `--realtime`: instead of one `.graph` span at the end
of a run, you get a stream of `topology.node.*` / `tool.*` / `llm.*` signal
spans as each boundary is crossed. That answers "can I see activity while
the run is still going." This section answers the follow-up: can the
**knowledge graph** stay current too, or only the flat span log?

Nothing in `normalize_otel` or `neo4j_push` cares whether the spans file is
finished or still growing — both just read whatever is in the file right
now. So the same two steps from §1 and §3 work unchanged on a realtime spans
file; you just re-run them periodically instead of once, after the run
finishes.

```bash
mas-lab telemetry convert library-telemetry/examples/qa-agent/events.jsonl \
  -o /tmp/t8-realtime-spans.jsonl --app-name qa-agent --realtime

mas-lab kg normalize --otel /tmp/t8-realtime-spans.jsonl \
  -o /tmp/t8-realtime-kg.jsonld --run-id t8-realtime

mas-lab kg neo4j-push /tmp/t8-realtime-kg.jsonld --dry-run
```

Swap the first command for a live agent run with the
`observability-otel-realtime` overlay from Tutorial 7 §6 and the spans file
grows while the agent is still executing. The second and third commands are
what you'd run on a timer (every few seconds, or after every N new lines)
against that same, growing file.

### Why re-running on the whole growing file, not just the new lines, is safe

Re-running `normalize_otel` on the whole file each tick looks wasteful —
isn't it reprocessing spans you already pushed? It is, and that's
deliberate, not an oversight:

- Node and edge ids are deterministic, derived from the call/span ids in the
  spans themselves, not assigned sequentially. The span-id-reuse fix from
  Tutorial 7 §6 (`topology.node.started`/`.completed` sharing one span id)
  is what makes this hold for realtime signals specifically — before that
  fix, a "started" and "completed" signal for the same logical call minted
  two different ids and would have produced two disconnected nodes instead
  of one node whose state fills in over time.
- `neo4j-push`'s generated Cypher uses `MERGE`, not `CREATE`, for every node
  and every edge (confirm with `--dry-run`, which prints the statements
  without connecting). Pushing the same node or edge again is a no-op;
  pushing one with new properties updates it in place.

Together, that means "normalize the full file so far, push it again" always
converges to the same graph a single end-of-run normalize would have
produced — it's just visible sooner, and each tick's graph is a strict
superset of the previous tick's.

### What this is not: true incremental ingestion

Reprocessing the whole file every tick is what makes today's approach safe,
and it's also its limitation. `normalize_otel` (both the OSS copy here and
OXP's own `norm.normalize()` underneath it) builds a fresh in-memory
`Registry()` on every call — there's no state carried between calls. A tick
that normalized only the spans written *since the last tick* would miss
nodes from earlier ticks entirely, so a tool-call signal would have no
`AgentCall` to attach to and would come out disconnected. That's why this
section's commands normalize the whole file rather than a delta.

For a short tutorial-sized run, renormalizing everything on a timer is
fine. It does not scale to a long-running production agent, where the spans
file (or whatever replaces it) keeps growing for as long as the agent runs.
Two things would need to exist before this became a real streaming
pipeline rather than "replay the file so far on a timer":

- **An actual event stream**, not a file or a batch query. Today's two
  realtime sources are a growing JSONL file (this section) and a live OTLP
  collector writing into ClickHouse (Tutorial 7 §6's live-plugin path) —
  neither gives you a cursor or offset to resume from, only "everything up
  to now."
- **An incremental registry** in `norm`/`mas-library-kg`, so a tick could
  hand it only the new spans and get back a graph merged with what it
  already knew, instead of rebuilding `Registry()` from nothing every time.

Both are future infrastructure work, not implemented here; this section
documents the honest state today: realtime KG viewing works, by replaying
the growing file, not by streaming deltas into persistent graph state.

---

## Key takeaways

1. **OTel → KG** reuses OXP's own `norm` package; **native → KG** is
   first-party. Both target `oxp_ontology.models.*`.
2. **CLI commands** (`kg normalize`, `kg neo4j-push`) are shortcuts to
   pipeline steps. File path vs `--infra` is the same serialize-to-file /
   serialize-to-service split as Tutorial 7.
3. **`$NEO4J_URI`** skips the YAML infra file. `--dry-run` does not need Neo4j
   running.
4. **Categories** (`include_trajectory` / `include_provenance` /
   `include_governance` / `include_infrastructure`) match the OTel export
   layers from Tutorial 7. Governance is off unless you opt in.
5. **Equivalence** is the contract that the two KG views stay aligned.
6. **Realtime KG today** means re-normalizing the whole growing spans file
   on a timer and pushing again — safe because ids are deterministic and
   `neo4j-push` uses `MERGE`, but not true incremental ingestion: there's no
   cross-tick registry state yet, so each tick reprocesses everything seen
   so far rather than just the new spans.
