# Comparing two Knowledge Graphs

Structural KG parity checks live in **mas-lab-graph** (`CompareKGStep`, step type
`compare_kg`). Algorithms compare agent coverage, node/edge types, delegation
topology, and tool usage — not byte-identical JSON.

## When to use

| Goal | Approach |
|------|----------|
| Native vs OTel-replay KG | `library-kg/pipelines/compare-two-kg.yaml` after `native-to-kg` + `native-to-kg-via-otel` |
| Native vs live plugin KGs | `library-kg/pipelines/compare-three-kg.yaml` (exp2 triple-obs) |
| Ad-hoc two files | `compare_kg` config with `reference_kg` / `candidate_kg` paths |

## Benchmark-embedded (design time)

```yaml
run:
  post:
    - ref: kg:native-to-kg
    - ref: telemetry:native-to-kg-via-otel
    - ref: kg:compare-two-kg
```

## CLI attach (run time)

```bash
mas-lab benchmark run my/experiment.yaml \
  --pipeline run:kg:native-to-kg \
  --pipeline run:telemetry:native-to-kg-via-otel \
  --pipeline run:kg:compare-two-kg
```

## Standalone on existing runs

After benchmark output exists under `data/experiments/<name>/`:

```bash
mas-lab benchmark pipeline run \
  thirdparty/mas-lab-internal/library-kg/pipelines/compare-two-kg.yaml \
  -o data/experiments/<name>
```

Ensure both `kg.jsonld` and `kg_otel.json` exist per run directory, or override
`reference_artifact` / `candidate_artifact` in the pipeline YAML.

## Output

`parity_report.json` (or `report_filename` override) with `{passed, checks, summary}`.
Step module: `mas-lab-graph/src/mas/lab/graph/steps/compare_kg.py`.

Batch API for offline use: `build_kg_document` in `mas.library.kg.pipeline`.
