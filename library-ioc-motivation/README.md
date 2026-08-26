# library-ioc-motivation

Reproduces the **IoC cognitive-challenge demonstration** using native MAS-Lab primitives —
an **Experiment** (baseline + challenge overlays × N reps over a seed query) and a
**Pipeline** (13-metric cognitive judge → baseline-vs-overlay delta → challenge×metric
heatmap). It is the platform-native equivalent of the bespoke "IoC Motivation" page.

**Scope: SRE-triage first.** Trip-planner is a follow-up (see §Roadmap).

The eval **logic stays in `ioc-core-mas-lab`** (`eval/run_eval.sh`, `delta_report.py`,
`build_bundle.py`, `query_sweep/replay_events_to_spans.py`). This library holds only the
**platform integration**: two thin step adapters + the experiment/pipeline/overlays/dataset.

## Layout
```
library.yaml            # kind: Library — registers the two step plugins
pyproject.toml          # makes mas.library.ioc_motivation importable (install to register steps)
src/mas/library/ioc_motivation/steps/
  ioc_cognitive_eval.py # 13-metric judge over experiment traces (adapter → ioc-core eval)
  ioc_delta.py          # baseline-vs-overlay delta/verdict + ablation_matrix (adapter → delta_report.py)
overlays/               # the 4 SRE challenge overlays (role-patches)
datasets/sre-queries.yaml
experiments/ioc-sre-reproduction.experiment.yaml
pipelines/ioc-cognitive-eval.pipeline.yaml
```

## Install (required — steps won't register otherwise)
The UI/registry only discovers a **library** (a dir with `library.yaml`); a `.lab` is not
UI-discoverable. And the step plugins are Python modules, so the package must be importable:
```
pip install -e library-ioc-motivation
```
Place the library where the controller discovers libraries (`MAS_LIBRARIES_DIR` /
`discover_library_roots()`), alongside `library-lab`, `library-samples`.

## Environment (the eval steps read these)
The steps shell out to ioc-core + claris; set:
- `IOC_REPO`       → the ioc-core-mas-lab checkout (has `eval/`)
- `MAS_LAB_OSS`    → this OSS mas-lab checkout (its `.venv/bin/python` runs the span converter)
- `CLARIS_LIB`     → the claris-lib checkout (the `paper_v2` 13-metric judge)
- `EVALUATOR_ENV`  → judge creds file (default `<IOC_REPO>/evaluator.env`)
- `MAS_CTL_MODEL`  → agent model for the experiment runs (SRE: `vertex_ai/gemini-2.5-flash`)

**Not self-contained:** the cognitive eval depends on the external `claris-lib` + judge
creds. That dependency is intentional (the 13-metric suite lives there), not a bug.

## Usage
1. **Run the experiment** (Experiments page, or `POST /api/libraries/.../benchmark/run` with
   `ioc-sre-reproduction`). Produces `baseline + 4 challenges × n_runs` traces natively.
2. **Run the pipeline** (Pipelines page, or `.../pipeline/run` with `ioc-cognitive-eval`) —
   or bind it as the experiment's `post` hook so it scores automatically. Outputs
   `metrics_long.csv`, the delta `report.json` (verdict/footprint), and the Fig-4
   `ablation_heatmap`.
3. **Read results** in the native Experiment/Pipeline results views.

## Proper-usage considerations (read before trusting numbers)
- **Delta over baseline, never absolute.** A metric failing under an overlay only counts if
  it fails *more than at baseline*. The `ioc_delta` step computes this.
- **Saturated metrics are not evidence.** If the baseline already fails a metric (≥80%),
  there's no headroom — it's flagged `saturated`, never `reproduced`.
- **N matters.** N=1 is a coin flip (rates ±100%); use `n_runs: 5` minimum, 10 to trust
  small deltas. Verdicts carry a confidence band; low-N "reproduced" reads as low-confidence.
- **Known-good result** (SRE, N=5): **CR-1 reproduces cleanly** (Goal Alignment 0%→~80%),
  DR-1 partial/noisy, **CC-3 & DC-2 saturated** on their intended metric (report them via
  footprint, not a green check). Use this to sanity-check a fresh run.
- **Scenario naming is load-bearing.** Each `scenario.id` must equal the overlay filename
  stem *and* start with the challenge code (`DR-1…`), and the reference must be `baseline`.
  Attribution (`challenge_summary`, delta) keys on that prefix — a wrong id misattributes
  silently.
- **Domain token.** `ioc_cognitive_eval.config.service_name` (e.g. `sre-triage`) names the
  eval bundle so the evaluator routes the correct domain. Keep it matching the app.

## Known gap to verify on first run
`ioc_cognitive_eval` reshapes the experiment's native traces into the eval bundle. It assumes
each run dir has `events.jsonl` + a `run_info.json` carrying the scenario (see `_scenario_of`).
If the native experiment output tree differs, adjust `_scenario_of` / the glob in
`steps/ioc_cognitive_eval.py`. This is the one interface not yet verified end-to-end.

Also: when the pipeline runs **standalone**, set `cognitive_eval.config.runs_dir` to the
experiment's trace root; when **bound as an experiment post hook**, it defaults to the
experiment output dir.

## Roadmap
- **Trip-planner**: `library-samples/apps/trip-planner` is the neutral OSS app — it **lacks
  the attraction/accessibility tools + dataset** the DR-1/DC-2 overlays need. Port the
  `trip-planner-ioc` tools+dataset (and note its baseline is *loaded*/saturated, so its
  deltas are weaker than SRE's).
- **Failure-pathway graph (paper Fig 3)**: net-new (no native metric-transition graph). It's
  the paper's real per-challenge discriminator — a later lift (failure-ordering data builder +
  a graph renderer), not part of this reproduction.
