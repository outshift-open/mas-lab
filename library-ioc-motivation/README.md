# library-ioc-motivation

Reproduces the **IoC cognitive-challenge demonstration** using native MAS-Lab primitives —
an **Experiment** (baseline + challenge overlays × N reps over a seed query) and a
**Pipeline** (13-metric cognitive judge → baseline-vs-overlay delta → challenge×metric
heatmap). It is the platform-native equivalent of the bespoke "IoC Motivation" page.

**Scope: two apps — `sre-triage` and `trip-planner-ioc`.** SRE has a comparatively clean
baseline (headroom for clean reproductions); trip-planner's baseline is *loaded* — many
metrics already fail with no overlay — so fewer challenges have headroom there (see
§Trip-planner caveats).

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
apps/sre-triage/                     # SRE MAS (gemini-2.5-flash)
apps/trip-planner-ioc/               # trip-planner MAS (gemini-2.5-flash)
overlays/                            # SRE challenge overlays (global namespace) + baseline.yaml (shared no-op)
apps/trip-planner-ioc/overlays/      # trip challenge overlays (namespace: trip-planner-ioc)
datasets/sre-queries.yaml
datasets/trip-planner-queries.yaml
experiments/ioc-sre-reproduction.yaml
experiments/ioc-trip-planner-reproduction.yaml
pipelines/ioc-cognitive-eval.yaml            # SRE       (service_name: sre-triage)
pipelines/ioc-trip-cognitive-eval.yaml       # trip      (service_name: trip-planner)
```

**Naming convention:** every app / overlay / dataset / experiment / pipeline has
`metadata.name` (experiments use `experiment.name`) equal to its file/folder name, with the
challenge **code prefix uppercase** (`DR-1`, `DC-2`, `CC-3`, `CR-1`). The uppercase code and
the `ref:` casing are load-bearing (see §Proper-usage); the `metadata.name` itself is
cosmetic (overlays resolve by path).

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
- `EVALUATOR_ENV`  → judge creds file (default `<IOC_REPO>/.env.evaluator`)
- `MAS_CTL_MODEL`  → agent model override. Both apps pin `vertex_ai/gemini-2.5-flash` in
  their manifests, so **leave this unset**. If set, it **overrides the manifest everywhere**
  (`ctl/.../engine_factory.py:resolve_model_name`), for
  both `mas-ctl` and the benchmark runner — so leave it unset to honor the per-app model,
  or set it deliberately. A wrong value (e.g. `gpt-4o-mini`) collapses heavy-overlay
  challenges into one-shot, tool-less traces the judge then discards.

- `MAS_CONTROLLER_IDLE_SEC` → controller idle auto-shutdown, **default 30s** (`sessions.py`).
  Long experiment/pipeline runs need this set high or the controller exits mid-run.

**Not self-contained:** the cognitive eval depends on the external `claris-lib` + judge
creds. That dependency is intentional (the 13-metric suite lives there), not a bug.

### Starting the controller
Both apps pin `vertex_ai/gemini-2.5-flash` in their manifests, so leave `MAS_CTL_MODEL`
**unset** — one controller serves both, no per-app restart:

```bash
MAS_CONTROLLER_IDLE_SEC=999999 mas-lab serve
```

- `MAS_CONTROLLER_IDLE_SEC` must be high or the controller auto-shuts-down mid-run
  (default **30s**, `controller/sessions.py`).
- Ensure **no stale `MAS_CTL_MODEL`** — it was hard-set in `mas-lab/.env` (`azure/gpt-4o-mini`)
  and now removed. It overrides *every* manifest, so a lurking value silently drives all apps
  on the wrong model (a weak one like `gpt-4o-mini` collapses heavy overlays; see §Environment).
- **Trip model note:** the paper's overlay-driven set used `gemma-4-26b-a4b-it-node4-h100`, but
  that's **403 on the proxy key**, so trip is pinned to `gemini-2.5-flash` here (faster than
  gpt-4o; diverges from the paper's gemma-4 for trip — unavoidable without gemma access).

## Usage
Two matched experiment+pipeline pairs — pick the app:

| app | experiment | pipeline (`service_name`) |
|-----|------------|---------------------------|
| SRE-triage | `ioc-sre-reproduction` | `ioc-cognitive-eval` (`sre-triage`) |
| trip-planner | `ioc-trip-planner-reproduction` | `ioc-trip-cognitive-eval` (`trip-planner`) |

1. **Run the experiment** (Experiments page, or `POST /api/libraries/.../benchmark/run`).
   Produces `baseline + 4 challenges × n_runs` traces natively.
2. **Run the matching pipeline** (Pipelines page, or `.../pipeline/run`) — or bind it as the
   experiment's `post` hook so it scores automatically. Outputs `metrics_long.csv`, the delta
   `report.json` (verdict/footprint), and the Fig-4 `ablation_heatmap`. (The pipeline eval is
   billable + can take 20+ min; the pipeline-run timeout was raised to 1h.)
3. **Read results** in the native Experiment/Pipeline results views.

## Proper-usage considerations (read before trusting numbers)
- **Delta over baseline, never absolute.** A metric failing under an overlay only counts if
  it fails *more than at baseline*. The `ioc_delta` step computes this.
- **Saturated metrics are not evidence.** If the baseline already fails a metric (≥80%),
  there's no headroom — it's flagged `saturated`, never `reproduced`.
- **N matters.** N=1 is a coin flip (rates ±100%); use `n_runs: 5` minimum, 10 to trust
  small deltas. Verdicts carry a confidence band; low-N "reproduced" reads as low-confidence.
- **Known-good result** (SRE, library app, N=5): **CR-1 reproduces cleanly** (Goal Alignment
  0%→100%). CC-3 & DC-2 are **saturated** on their intended metric (Verification Quality /
  Instruction Following already fail at baseline), DR-1 partial/noisy. Report saturated ones
  via footprint, not a green check.
- **Baselines are noisy at low N.** Independent N=5 baseline runs of the *same* app can swing
  a metric 0%↔80% (LLM-judge + agent stochasticity). Use **N≥20** for a stable baseline; at
  N=5 only extreme, repeatable jumps (like CR-1 0→100%) are trustworthy. Note also the two
  `sre-triage` app copies differ — the **library** app gave Goal Alignment baseline ~0% (CR-1
  clean), the **ioc-core** app ~55% (CR-1 tight); pick one canonical app per cohort.
- **Scenario naming is load-bearing.** Each `scenario.id` must equal the overlay filename
  stem *and* start with the challenge code (`DR-1…`), and the reference must be `baseline`.
  Attribution (`challenge_summary`, delta) keys on that prefix — a wrong id misattributes
  silently.
- **Domain token.** `ioc_cognitive_eval.config.service_name` (e.g. `sre-triage`) names the
  eval bundle so the evaluator routes the correct domain. Keep it matching the app.

## Trip-planner caveats
- **Loaded baseline (N=20):** trip-planner fails most metrics with no overlay — Delegation
  Accuracy 95%, Communication Efficiency 90%, Constraint Satisfaction 90%, Instruction
  Following 85%, Context Preservation 75%, Goal Alignment 70%, Verification Quality 70%.
  With the reproduce rule (`delta ≥ 0.4`), only **DR-1** (Semantic Consistency, baseline 40%)
  has headroom; **CC-3, DC-2, CR-1 are effectively unconfirmable on trip-planner** (their
  metric is already too high to gain +40pp). Use SRE for those.
- **Diverges from the paper baseline.** The paper reports low discriminator baselines
  (Goal Alignment 6%, Semantic Consistency 6%, Confidence Calibration 8%); our trip run is
  far higher (70% / 40% / 40%). Investigate model/app-version before treating trip deltas as
  paper-comparable.
- **DR-1 / CR-1 overlays fail standalone `mas-ctl validate`** — they inject agent tool refs
  (`../../tools/…`) that resolve correctly at compose time (agent-relative) but not to the
  standalone validator (overlay-relative). This is harmless for the **native runner** (the
  benchmark composes with `validate=False`) and for `mas-ctl` **with `--no-validate`**; only a
  bare `mas-ctl run-mas`/`validate` rejects them. DC-2 / CC-3 validate cleanly.
- **Overlays are app-namespaced** in `apps/trip-planner-ioc/overlays/` with
  `metadata.namespace: trip-planner-ioc` — the platform convention (`create_overlay`):
  namespace `global` → `overlays/`, anything else → `apps/<namespace>/overlays/`, and the
  namespace field is what the UI lists them under. This both avoids the
  `CR-1-divergent-goal.yaml` filename collision with the SRE overlays and makes them appear
  under the trip namespace (putting them in a bare `overlays/<subdir>/` does **not** work —
  the registry doesn't scan it). The shared no-op `overlays/baseline.yaml` stays global.
  (The SRE IoC overlays remain global in `overlays/`; they could be moved to
  `apps/sre-triage/overlays/` with `namespace: sre-triage` for symmetry, but global works
  since their names don't collide.)

## Known gap to verify on first run
`ioc_cognitive_eval` reshapes the experiment's native traces into the eval bundle. It assumes
each run dir has `events.jsonl` + a `run_info.json` carrying the scenario (see `_scenario_of`).
If the native experiment output tree differs, adjust `_scenario_of` / the glob in
`steps/ioc_cognitive_eval.py`. This is the one interface not yet verified end-to-end.

Also: when the pipeline runs **standalone**, set `cognitive_eval.config.runs_dir` to the
experiment's trace root; when **bound as an experiment post hook**, it defaults to the
experiment output dir.

## Roadmap
- ~~**Trip-planner**~~ **Done** — `trip-planner-ioc` (app + tools + dataset) is ported with its
  experiment/pipeline. Its baseline is *loaded* (see §Trip-planner caveats), so only DR-1 has
  headroom there; SRE remains the vehicle for the other challenges.
- **More challenges**: only the 4 priority overlays (DR-1/DC-2/CC-3/CR-1) are wired per app.
  The taxonomy has 10 (CC-1, DC-1, DC-4, DE-1, CE-1, CS-1/EM-1…); add overlays + extend
  `delta_report.INTENDED` to keep the verdict in sync with claris `CHALLENGE_METRIC`.
- **Failure-pathway graph (paper Fig 3)**: net-new (no native metric-transition graph). It's
  the paper's real per-challenge discriminator for the saturated metrics — a later lift
  (failure-ordering data builder + a graph renderer), not part of this reproduction.
