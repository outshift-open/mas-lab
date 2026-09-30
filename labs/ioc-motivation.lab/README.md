<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->

# IoC Motivation — running the reproduction experiments

IoC cognitive-challenge **reproduction experiments** on the
`sre-triage` app. They ship in the **`library-ioc-motivation`** library; this page shows how
to run them from either the **UI** or the **CLI**.

Each experiment runs a baseline scenario plus per-challenge overlays (`CR-1`, `DC-2`,
`CC-3`, `DR-1`, …) over a seed incident query, `n_runs` times, producing agent traces you
can inspect in the Experiment views.

| Experiment             | Coordination                                  | Scenarios                         |
| ---------------------- | --------------------------------------------- | --------------------------------- |
| `ioc-sre-reproduction` | Centralized — sre-orchestrator delegates      | baseline + 8 challenge overlays   |
| `ioc-sre-debate`       | Decentralized — `deterministic_staged_debate` | baseline-debate + debate overlays |

> ⚠️ **Experiments only, for now.** You can (re)run the experiments to **generate traces** —
> that's what this library supports today. The pipeline that computes the **cognitive metrics
> and plots** from those traces is **not yet released** (it depends on unreleased dependecies), so
> metric/heatmap computation is **not available here**. The steps below cover trace
> generation only.

## Load the precomputed outputs (`ioc-motivation.zip`)

If you just want to **look at outputs computed elsewhere** — no re-run, no LLM endpoint, no
install — import the shared archive. `ioc-motivation.zip` contains two folders, one per
experiment, each a full experiment output tree
(`<scenario>/itemctx-1/r<N>/{run_info.json, traces/events.jsonl}` plus `metadata.yaml`):

```
ioc-sre-reproduction/    # centralized experiment output
ioc-sre-debate/          # decentralized (debate) experiment output
```

**Download it** from the repo's
[Releases](https://github.com/outshift-open/mas-lab/releases) page (release
`data-ioc-motivation-v1.0`), or directly:

```bash
curl -L -o ioc-motivation.zip \
  https://github.com/outshift-open/mas-lab/releases/download/data-ioc-motivation-v1.0/ioc-motivation.zip
```

**Then unzip it and drop both folders into your `labs/` directory.** Where that is depends on
how you run the controller:

| Setup                                        | Put the two folders under                                                      |
| -------------------------------------------- | ------------------------------------------------------------------------------ |
| **Non-Docker** (`mas-lab serve` on the host) | `~/.local/share/mas/labs/`                                                     |
| **Docker**                                   | `<MAS_DATA_MOUNT>/labs/` — your host data folder (e.g. `~/test-mas-lab/labs/`) |

Non-Docker:

```bash
unzip ioc-motivation.zip -d /tmp/ioc-motivation
mkdir -p ~/.local/share/mas/labs
cp -r /tmp/ioc-motivation/ioc-sre-reproduction \
      /tmp/ioc-motivation/ioc-sre-debate \
      ~/.local/share/mas/labs/
```

Docker — same, but into your `MAS_DATA_MOUNT` folder (the one bound to `/data`):

```bash
unzip ioc-motivation.zip -d /tmp/ioc-motivation
mkdir -p ~/test-mas-lab/labs
cp -r /tmp/ioc-motivation/ioc-sre-reproduction \
      /tmp/ioc-motivation/ioc-sre-debate \
      ~/test-mas-lab/labs/
```

Start (or restart) the controller, open the **Experiments** page, and both
`ioc-sre-reproduction` and `ioc-sre-debate` appear — read-only, straight from the files.
Keep the folder names exactly `ioc-sre-reproduction` / `ioc-sre-debate`; the controller lists
experiments by scanning `<labs root>/<name>/`, so a renamed folder won't match.

---

## Prerequisites to re-run the experiments

- **An LLM endpoint the runner can reach.** The `sre-triage` agents pin
  `vertex_ai/gemini-2.5-flash` (remapped by `standard:llm-proxy`); point the proxy at your
  endpoint via `LLM_PROXY_API_BASE` + the key env var, and **leave `MAS_CTL_MODEL` unset**
  (it overrides every manifest).
- **`MAS_CONTROLLER_IDLE_SEC`** set high, or the controller auto-shuts-down mid-run
  (default 30s).

Results are written to `$XDG_DATA_HOME/mas/labs/<experiment-name>/` (i.e.
`~/.local/share/mas/labs/…`; check with `mas-lab config`).

---

## Run via the UI

**Start the controller + UI:**

```bash
MAS_CONTROLLER_IDLE_SEC=999999 mas-lab serve
```

(or `docker compose up` from `docker/` — UI at http://localhost:8080).

Then, in the UI:

1. Go to the **Experiments** page.
2. Select the **`library-ioc-motivation`** library, then choose an experiment —
   **`ioc-sre-reproduction`** (centralized) or **`ioc-sre-debate`** (decentralized).
3. Click **Run**. Adjust `n_runs` / parallelism first if you want a smaller pass.
4. Watch live progress; when it finishes, open the run in the **Experiment results** view to
   inspect the per-scenario traces (`events.jsonl`), `run_info.json`, and summary files.

The UI calls `POST /api/libraries/library-ioc-motivation/benchmark/run` under the hood — the
same thing the CLI does.

---

## Run via the CLI

**Step 1 — start the controller** (experiments run through the daemon):

```bash
MAS_CONTROLLER_IDLE_SEC=999999 mas-lab serve
```

**Step 2 — run an experiment** from inside the library directory (so its relative `apps/…`
paths resolve):

```bash
cd library-ioc-motivation

# Centralized reproduction
cp experiments/ioc-sre-reproduction.yaml .
mas-lab benchmark run ioc-sre-reproduction.yaml --progress

# Decentralized debate
cp experiments/ioc-sre-debate.yaml .
mas-lab benchmark run experiments/ioc-sre-debate.yaml --progress
```

Useful flags:

| Flag                  | Effect                                                       |
| --------------------- | ------------------------------------------------------------ |
| `--max-runs N`        | override `n_runs` from the YAML                              |
| `--single-run`        | one scenario, one rep — fast smoke test                      |
| `--limit-scenarios N` | only the first N scenarios                                   |
| `-b` / `--background` | submit and return a worker id (poll with `benchmark follow`) |
| `--force`             | new run even if a cached one exists                          |
| `--dry-run`           | validate + show the plan, run nothing                        |

**Step 3 — find the output:**

```bash
ls ~/.local/share/mas/labs/ioc-sre-reproduction/   # or ioc-sre-debate/
```

Layout: `<scenario>/itemctx-1/r<N>/{run_info.json, traces/events.jsonl}`, plus
`metadata.yaml` and `results.csv`.

> **Trace cache:** results are content-addressed under `~/.cache/mas/traces`. Changing
> config (overlay/model) re-runs; changing only code does not — use `--force` or clear the
> cache to force a fresh run.

---

## Notes

- **Scoring is not available yet** (see the disclaimer above). These experiments only
  _generate traces_. Turning them into cognitive metrics and plots (the 13-metric judge,
  delta, heatmaps) requires the eval pipeline, whose code is **unreleased** and not shipped
  with this library.
- **N matters.** `n_runs: 1` is a coin flip; use 5 minimum, 20+ for a stable baseline.
