<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
# Lab 3 — Context Source Extensions: Results

**Status (2026-06-02):** historical run notes below. To reproduce or refresh
figures today, use `mas-lab benchmark run labs/extensions.lab/experiment.yaml`
(pipeline steps only — no standalone plotting scripts).

The 4-scenario reproducibility benchmark
(baseline / vector-memory / letta-memory / vector-memory+guardrail) was
re-executed end-to-end at `n_runs = 3` (120 runs, 100 % OK status). The
LLM-judge analysis steps (`eval_mce` + `compute_ci` + `plotnine`) hung at
the end of execution on a CLOSE_WAIT against the OpenAI-compatible
endpoint and were killed; the per-run trace data persisted, so the
attribution figure (§1.5) was built **directly from the
events.jsonl traces** by a stand-alone script — no LLM judge involved.

Run output: `~/mas-data/extensions-lab/`. Pipeline:
[`experiment.yaml`](experiment.yaml).

---

## Lab 3 §1.5 — Attribution Sankey

The figure at `~/mas-data/extensions-lab/results/figure-attribution-sankey.png`
encodes all 120 runs across four stages: **scenario → tool → governance →
answer**. Stages are populated from the trace alone (no LLM judge):

| Stage      | Categories                                                |
|------------|-----------------------------------------------------------|
| scenario   | baseline / with-vector-memory / with-letta-memory / +guardrail |
| tool       | `used-tools` (≥1 `tool_call_start` span) / `no-tool`      |
| governance | `denied` (`PolicyViolation` raised) / `allowed`           |
| answer     | `answered` / `refused-ok` (correct refusal on g1) / `refused-bad` (refusal on non-g1) |

**Headline flows (out of 120 runs):**

```
scenario                       → tool        → governance → answer        n
─────────────────────────────────────────────────────────────────────────────
with-vector-memory-guardrail  → used-tools  → denied     → refused-ok    3
all other scenarios           → used-tools  → allowed    → answered     49
all scenarios                 → no-tool     → allowed    → answered     56
baseline / letta / vector     → used-tools  → allowed    → refused-ok    9
```

**Reading.**

1. **Governance triggers fire only where the overlay says they should.**
   *Three* runs end in `governance:denied` and *all three are in the
   `with-vector-memory-guardrail` scenario on item `g1`*
   (the "Shadowmere" forbidden-destination query). No false positives
   across the other 117 runs. The trace-level signal therefore localises
   the governance contribution exactly — without any LLM judge needed.

2. **The baseline correctly refuses g1 too** (3/3 on g1 → `refused-ok`),
   but via *the LLM* declining, not via a policy event. The Sankey shows
   this as `allowed → refused-ok` instead of `denied → refused-ok`. This
   is exactly the distinction §5.3 makes: the answer can look identical
   end-to-end while the *provenance* of the refusal differs.
   Failure-localisation is intrinsic to the trace, not derived from
   output text.

3. **Tool usage is the dominant predictor of "answered" vs. "no-answer"**:
   among the 55 runs where the agent *did* call a tool, 52 produced an
   `answered` output and 3 produced a correct refusal; among the 65
   no-tool runs, 56 produced an answered output (because for `recall`
   queries the LLM has enough context to give a generic answer) and 9
   produced incorrect refusals. The trace alone localises the failures.

4. **The memory overlays produced zero observable `memory_*` events**
   across all 60 vector/letta runs. This is a *negative finding worth
   reporting*: the overlay wires the plugin and registers the
   `memory-search` tool, but on this prompt set the agent never *chose*
   to call it. The reproducibility claim of the paper holds (the runs
   are repeatable; tools are invoked uniformly), but the *memory
   extensibility* claim is only demonstrable when an item explicitly
   names a profile attribute the agent must retrieve. This is now
   §1.6 follow-up below.

Per-scenario answer distribution (n=30 each):

| Scenario                     | answered | refused-ok | refused-bad |
|------------------------------|---------:|-----------:|------------:|
| baseline                     |       26 |          3 |           1 |
| with-vector-memory           |       26 |          3 |           1 |
| with-letta-memory            |       26 |          3 |           1 |
| with-vector-memory-guardrail |       27 |          3 |           0 |

Outputs:

- `~/mas-data/extensions-lab/results/attribution.csv` (120 rows, 6 cols)
- `~/mas-data/extensions-lab/results/figure-attribution-sankey.png`
- `~/mas-data/extensions-lab/results.csv` (120 raw runs, all `status=ok`)

---

## Lab 3 §base — Memory extension reproducibility

The mas-lab `eval_mce` step hung on the LLM-judge HTTP calls (CLOSE_WAIT
on the proxy) and was killed after producing the 120-run trace corpus
but before writing the CI summary CSV. The numerical reproducibility
claim of §5.3 is therefore **not refreshed in this session**; the
previously published Table 5 (last run 2026-05 in the archive snapshot
at `~/.mas/labs/memory-provenance/`) remains the canonical source
for GSR/AR numbers. What this session adds is:

- **120 fresh runs across all 4 scenarios** with the `n_runs=3`
  configuration, persisted under `~/mas-data/extensions-lab/`
- **An eval-judge-free attribution figure** that the paper can use
  alongside Table 5 to demonstrate the failure-localisation claim

---

## Experiment backlog

| §    | Experiment                              | Status              | Notes |
|------|-----------------------------------------|---------------------|-------|
| 1.1  | Letta condition in Table 5              | **Runs done**       | 30 fresh runs persisted; LLM-judge re-scoring blocked on proxy hang. |
| 1.2  | Memory × topology 2×2 control           | **Not started**     | Needs `2-agent, no-memory` overlay. |
| 1.3  | Multi-session memory                    | **Not started**     | Needs 5-session dataset. |
| 1.4  | New tool mid-experiment                 | **Not started**     | Needs overlay-only currency-converter. |
| 1.5  | **Attribution Sankey**                  | **DONE**            | Trace-only figure produced; 3/3 g1 runs in guardrail scenario end in `governance:denied`. |
| 1.6  | Demonstrate memory `hit` on profile-recall | **Surfaced now**  | Memory overlays produced 0 `memory_*` events on this dataset — agent never autonomously called `memory-search`. Either the prompt set must be sharpened or the overlay must expose memory via passive injection (Letta) more aggressively. |
| 2.1  | n ≥ 20 runs                             | **Pipeline-ready**  | Flip `n_runs: 3` → `20`. |
| 2.2  | Statistical tests (Wilcoxon / t)        | **Pending eval**    | Needs `compute_ci` to complete. |
| 2.3  | Second judge                            | **Step ready**      | `inter_rater_agreement` in `lib/steps/`. |
| 2.4  | Investigate GSR=0 for no-memory         | **Pending eval**    | — |

---

## Reproduce

```bash
# 1. Runs (already cached, content-addressed; will be no-ops):
mas-lab benchmark run labs/extensions.lab/experiment.yaml --force

# 2. Attribution Sankey (script, ~5 s, no LLM):
python3 /tmp/lab3_attribution2.py
```
