<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# CLI observability reference

How **`events.jsonl`** run logs, the **exchange log**, and CLI flags relate to
**manifests**, **overlays**, and **observability** settings.

Applies to `mas-ctl chat`, `mas-ctl tui`, `mas-ctl run-mas`, and (for
**benchmarks**) `mas-lab benchmark run`.

Command-line flags (all of `--trace*` / `--events*`): [mas-ctl.md](mas-ctl.md).
`config.yaml` keys: [config.yaml reference](../references/config.yaml.md).

Term definitions: [glossary.md](../glossary.md).

---

## Three outputs (do not confuse them)

| Output | What it is | Primary consumer |
|--------|------------|------------------|
| **`events.jsonl`** | Machine-readable **run** log — one JSON object per line | **Pipeline steps** (`extract_trace_stats`, `eval_mce`), `mas-lab telemetry`, plots |
| **Exchange log** | Human-readable AGENT↔LLM↔TOOL transcript on **stderr** | Interactive debugging (`mas-ctl chat --trace`) |
| **OTel spans** | OpenTelemetry export (optional second sink) | External collectors (`--events-format otel`) |

Structural claims in **experiments** (governance fired, tool counts, HITL gates)
must be checked from **`events.jsonl`**, not from the exchange log.

---

## Enable `events.jsonl`

### 1. Manifest (persistent)

Add **observability** to the **agent** or **MAS** manifest:

```yaml
spec:
  observability:
    enabled: true
    format: native          # native | boundary | both | otel
    events_file: traces/events.jsonl
```

### 2. Overlay (recommended for experiments)

An **overlay** is a patch file merged onto the manifest. Use the standard
observability overlay:

```bash
mas-ctl chat agent.yaml -o docs/schemas/examples/overlays/observability-native.yaml
mas-ctl run-mas mas.yaml -o docs/schemas/examples/overlays/observability-native.yaml
```

Example overlay: [schemas/examples/overlays/observability-native.yaml](../schemas/examples/overlays/observability-native.yaml)

### 3. CLI flags (session override)

On **`mas-ctl chat`**, **`mas-ctl tui`**, and **`mas-ctl run-mas`** — override the
manifest for one session:

| Flag | Effect |
|------|--------|
| `--events` / `--no-events` | Force observability on or off |
| `--events-file PATH` | JSONL path (default `traces/events.jsonl` under run cwd) |
| `--events-stdout` | Also stream JSONL records on **stderr** |
| `--events-format FORMAT` | `native`, `boundary`, `both`, or `otel` |

**Shortcut:** `--events` is equivalent to the `observability-native` **overlay** for
one run. For **benchmarks**, prefer overlay or manifest so every **scenario** sees
the same settings.

```bash
mas-ctl chat agent.yaml -i \
  --events \
  --events-file logs/events.jsonl \
  --events-format native
```

### Equivalence table

| Goal | Manifest | Overlay | CLI |
|------|----------|---------|-----|
| Native `events.jsonl` | `spec.observability.enabled: true` | `observability-native.yaml` | `--events` |
| Custom path | `events_file:` | patch `events_file` | `--events-file PATH` |
| Stream JSONL to terminal | — | — | `--events-stdout` |
| Boundary + native | `format: both` | — | `--events-format both` |
| OTel spans in file | `format: otel` | — | `--events-format otel` |

---

## Exchange log (interactive trace)

Separate from **`events.jsonl`**: a pretty-printed view of structured
`ExchangeRecord` hops on **stderr** for **`mas-ctl chat`** / **`run-mas`**.
Stdout stays the conversation. `--trace` is the compact summary; `--trace full`
pretty-prints payloads last. Humans use this log; machines use **`events.jsonl`**
/ **`mas-lab telemetry`**.

Full flag and `config.yaml` tables: [mas-ctl.md](mas-ctl.md#exchange-log) ·
[config.yaml `mas_ctl`](../references/config.yaml.md#mas_ctl).

```bash
mas-ctl chat agent.yaml -i --trace
mas-ctl chat agent.yaml -i --trace full
mas-ctl chat agent.yaml -i --trace --trace-color
```

Headers keep the raw hop (`TOOL[activate_skill]`) and, when the tool
advertised `spec.semantics` / `list_tools().semantics`, an interpretation
(`SKILL[answer-formatting]`, `MEMORY[write]`). The model id is the engine's
resolved model (`spec.models`, `--model` / `MAS_CTL_MODEL`), never a
label-only fallback.

---

## `events.jsonl` record shape

Common `kind` values (native transform):

| Kind | Meaning |
|------|---------|
| `execution_start`, `execution_end` | **Run** lifecycle |
| `llm_call_start`, `llm_call_end` | Model call (latency on `_end`). `llm_call_end.tools` is the function names sent to the model on that call. |
| `context_assembled` | Prompt snapshot for that call. `tools` is the same function-name list. |
| `tool_call_start`, `tool_call_end` | Tool call |
| `governance_event`, `governance_policy` | Policy / budget hooks |
| `routing`, `routing_result` | Delegation between agents in a **MAS** |

After a **benchmark**, logs are stored at:

```text
<output_dir>/<scenario>/item<N>/r<N>/traces/events.jsonl
```

With **trace cache** enabled, the path may be a link to a shared copy; **pipeline
steps** resolve it automatically.

---

## `mas-lab telemetry` (post-run)

```bash
mas-lab telemetry show  path/to/traces/events.jsonl
mas-lab telemetry dump  path/to/traces/events.jsonl
mas-lab telemetry push  path/to/traces/events.jsonl --endpoint http://localhost:4318
```

---

## Benchmarks and observability

`mas-lab benchmark run experiment.yaml` does **not** take `--events`. **Observability**
is configured through:

1. **Flavour** (`experiment.yaml` → instrumentation preset)
2. **Overlays** on **scenarios** or the app
3. App defaults in the bundled MAS

The **embedded pipeline** in `experiment.yaml` runs after execution:

```bash
mas-lab benchmark run labs/lifecycle-control.lab/experiment.yaml --progress
```

See [Tutorial 3](../tutorials/03-experiments-and-analysis/README.md) for pipeline
and figure workflows.

---

## Related

- [ctl/tui.md](../ctl/tui.md) — same `--events*` flags
- [Web UI](../ui/index.md) — browse **run** artifacts
- [glossary.md](../glossary.md) — manifest terms
