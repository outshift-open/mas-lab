<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Tutorial 10 — Evaluation metrics

> **Packages:** `mas-lab`, `mas-library-eval`
> **Prerequisite:** [Tutorial 3](../03-experiments-and-analysis/) — you have
> already run an experiment, inspected `events.jsonl`, and scored a run with
> stock MCE.

Tutorial 3 answers one kind of question: *does this session look like a good
answer?* Groundedness, goal success, relevancy — those prompts belong to MCE,
and mas-lab only chooses the **judge model**.

This tutorial is about the next problem you hit in a real lab: **that is not
the question you needed**. You wanted to know whether a tool fired, whether
two specialists contradicted each other, whether a protocol activated. Those
are still session scores in `metrics.json`. They are not stock MCE.

You will:

1. recall what a session metric is, and where it is written;
2. score a run with stock MCE (the Tutorial 3 path);
3. define an inline metric (prompt plus what evidence it needs);
4. promote a reusable metric by registering it on the MCE eval provider;
5. attach a mixed pipeline to a finished run.

Attach pipelines explicitly. A file named `pipeline.yaml` next to the
experiment is not enough.

```bash
mas-lab benchmark … --pipeline run:post:path/to/eval-pipeline.yaml
```

---

## The problem

A finished run is a folder with `traces/events.jsonl`. Evaluation is a
**post** step: it reads that trace and writes `metrics.json` beside
`run_info.json`. Each id in `session` is one question:

```json
{
  "schema_version": "1",
  "session": {
    "groundedness": {
      "value": 0.8,
      "reasoning": "…",
      "error": null
    }
  }
}
```

`value` is a number or `null`. Optional `details` holds structured extras
(gates, token buckets, the judge payload). **Polarity is per id** — document
it next to the name. `1.0` is not always “good”.

The **metric** knows what input it needs. The step only names ids and
writes `metrics.json`. Stock MCE metrics look at MAS input/output (the
user query and the final answer). They do not see the event list. A
metric that asks “did a tool fire?” must say it needs the trajectory —
that belongs in the metric definition, not as a switch on `eval_mce`.

On a metric, two fields make that contract readable:

| Field | Values | Meaning |
|---|---|---|
| **unit** | `mas`, `agent`, `call` | Which I/O pair: the whole MAS run, one agent, or one LLM/tool call |
| **evidence** | `io`, `trajectory` | Only that pair's input and output, or the event history |

They are stored on `details.unit` / `details.evidence`. `unit: call` is
not implemented in this release (`metrics.json` is one score per run).

Three ways to ship a metric, all listed on the same `eval_mce` step:

| You need… | Do this | The metric's input |
|---|---|---|
| Generic quality wording MCE already ships | List the stock id | MAS I/O (built into MCE) |
| A question that exists only for this experiment | Inline definition under `prompt_metrics` | `unit` + `evidence` on that definition |
| A reusable definition with tests | `eval_metric` plugin on the MCE provider | `unit` + `evidence` on the class (default: MAS trajectory) |

Start with the cheapest layer that answers the question. Promote only when
the same wording is going to live in more than one pipeline.

---

## Part A — Stock MCE (Tutorial 3, revisited)

List ids. Omit `metrics` and you get every session metric in `METRIC_MAP`.

```yaml
- name: eval
  type: eval_mce
  per_run: true
  in: trace
  out: metrics
  config:
    metrics:
      - groundedness
      - goal_success_rate
      - context_preservation
```

| Id | Asks |
|---|---|
| `answer_relevancy` | Is the response relevant to the query? |
| `goal_success_rate` | Did the agent accomplish the user's goal? |
| `groundedness` | Is the response grounded in retrieved context? |
| `response_completeness` | Does the response address the query? |
| `workflow_cohesion_index` | How cohesive was multi-agent coordination? |
| `workflow_efficiency` | Was the workflow efficient? |
| `consistency` | Were responses consistent across turns? |
| `context_preservation` | Was conversational context preserved? |
| `information_retention` | Was key information retained? |
| `intent_recognition_accuracy` | Was user intent identified? |
| `component_conflict_rate` | How often did component outputs conflict? |

MCE owns those prompts. The runner extracts **MAS input** (`input_query`
from the root `execution_start`) and **MAS output** (`final_response`
from the response agent). That is I/O of the run, not the trajectory.
If two systems both say “groundedness”, they are not the same
definition — prefix or document colliding names.

The judge **model** is a lab field. Resolution order (first hit wins):

1. `eval_mce` `config.model` / `config.judge_model`
2. `experiment.evaluation.model`
3. `experiment.models.judge`
4. `experiment.model` / `models.main`
5. application `spec.models[]`

Runnable pin: [library-eval/examples/mce/judge-override/](../../../library-eval/examples/mce/judge-override/).
Full table: [summarization.md — MCE judge model](../../manifests/summarization.md#mce-judge-model).

---

## Part B — An inline metric

Suppose Tutorial 3's groundedness score is fine, but you also need: *did
the agent invoke a tool?* That question is not in MCE. You do not need a
plugin yet. The YAML **is** the metric — id, what it needs, and the
prompt it owns.

```yaml
config:
  metrics: [groundedness]
  prompt_metrics:
    - id: used_a_tool
      description: 1.0 if the run invoked at least one tool.
      unit: mas
      evidence: trajectory
      prompt: >
        Did the agent invoke at least one tool?
        Return JSON {"value": 1.0 or 0.0, "reasoning": "cite a tool_call_start event"}.
    - id: answered_the_user
      unit: mas
      evidence: io
      prompt: >
        Given only INPUT (the user query) and OUTPUT (the final answer),
        did OUTPUT address INPUT?
        Return JSON {"value": 1.0 or 0.0, "reasoning": "…"}.
```

Required: snake_case `id`, `prompt`, `unit`, `evidence`. Optional:
`description`, `system`, `agent` (when `unit: agent`). `question` is an
alias for `prompt`. The helper that runs inline metrics appends the
requested slice after `---` (`## INPUT` / `## OUTPUT` for `io`,
`## TRACE` for `trajectory`). There is no default system prompt.

The step parses a JSON object with numeric `value`, or `answer: YES|NO`
(YES → 1.0). Put that contract in **your** prompt. Results land in
`session.used_a_tool` in the same `metrics.json`.

Ids must not collide with stock MCE or a registered `eval_metric`. When the
same wording is used in more than one lab, promote it (Part C).

---

## Part C — A reusable metric on the MCE provider

A content library ships metrics that experiments pin by id. They register
on the **existing MCE eval provider** — the same `EvalProvider` that
`register_provider` / `get_provider("mce")` already use. There is no
second registry.

```yaml
# library.yaml
types:
  - eval_metric
plugins:
  - type: eval_metric
    name: toy_echo
    module: mas.library.eval.metrics.toy
    class: ToyEchoMetric
    attributes:
      provider: mce
  - type: eval_metric
    name: my_family
    factory: mas.library.example.metrics:build_metrics
    attributes:
      provider: mce
```

```python
from mas.library.eval.metrics import EvalMetric, MetricContext, RunInputs
from mas.library.eval.metrics.llm_json import complete_json

class ToyEchoMetric(EvalMetric):
    metric_id = "toy_echo"
    unit = "mas"
    evidence = "trajectory"
    requires_llm = False

    async def compute(self, inputs: RunInputs, ctx: MetricContext):
        path = inputs.require("native_trace")
        return {
            "value": 1.0,
            "reasoning": f"{path.name} is present",
            "error": None,
            "details": {"bytes": path.stat().st_size},
        }
```

An LLM judge uses the **same** OpenAI-compatible client `eval_mce` already
installed (`install_openai_llm_service`). Call `complete_json(messages)` —
do not build a second HTTP client. Your messages are the whole prompt.

Rules:

- Duplicate ids raise at registration. Stock MCE session ids, plugins, and
  `prompt_metrics` all run on `get_provider("mce")`. Stock ids are MAS
  I/O. Set `unit` and `evidence` on a plugin class so the slice is
  explicit (defaults: `mas` + `trajectory`).
- `batch_key` groups a family so one parse / one `evaluate_file` serves
  many ids (`compute_batch`).
- A failing metric writes `{value: null, error: "…"}` for that id only.
- Split families across steps with distinct `metrics_filename` values if
  you want a second judge file (`metrics_judge2.json`).

List those ids in `eval_mce.config.metrics` together with stock MCE and
`prompt_metrics`.

---

## How the judge client is shared

`eval_mce` calls `install_openai_llm_service` before any judge runs. Stock
MCE, `complete_json`, and `llm_service_config()` (for an external scorer)
all use that client. They share credentials, retries, and the proxy URL.

They are **not** kernel `LLM_CALL` events, so runtime `llm_cache`
middleware does not automatically replay them. If the proxy itself records
OpenAI-compatible traffic, judge calls can still hit that gateway cache.

`complete_json` retries malformed JSON (appends a “JSON only” turn) on the
same client.

To wrap a trajectory scorer (history of tool results, open requirements,
hand-offs): prefer a pre-written `otel_sdk_spans.jsonl`, or convert with
the stock `events_to_otel` path; pass `llm_service_config()` into the
scorer; prefix ids (`stateful_groundedness`) so they never collide with
MCE `groundedness`; use `batch_key` so many codes share one call.

Deterministic counters (`extract_trace_stats`) are not `metrics.json`.
Cross-run reports (`metrics_to_dataframe`, impact steps) **read** scores;
they do not call the judge again.

---

## Try the mixed pipeline

[eval-pipeline.yaml](eval-pipeline.yaml) mixes the three sources: stock
`groundedness`, registered `toy_echo` (ships with `mas-library-eval`, no
LLM), and step-local `used_a_tool`.

From the repository root, after a Tutorial 3 (or any) run that produced
`traces/events.jsonl`:

```bash
mas-lab benchmark pipeline run \
  docs/tutorials/10-evaluation-metrics/eval-pipeline.yaml \
  -o <that-run-folder>
```

Or attach it on the next benchmark:

```bash
mas-lab benchmark run path/to/experiment.yaml \
  --pipeline run:post:docs/tutorials/10-evaluation-metrics/eval-pipeline.yaml
```

---

## See also

- [Tutorial 3](../03-experiments-and-analysis/) — first experiment and MCE
- [summarization.md — MCE judge model](../../manifests/summarization.md#mce-judge-model)
- [LLM cache](../../manifests/llm-cache.md)
- [pipeline-steps.md](../../../lab/docs/pipeline-steps.md) — `eval_mce`
- [library-eval README](../../../library-eval/README.md)
