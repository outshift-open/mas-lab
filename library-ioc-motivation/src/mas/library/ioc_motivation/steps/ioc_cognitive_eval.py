#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ioc_cognitive_eval — run the IoC 13-metric cognitive judge over experiment traces.

Thin adapter over ioc-core's ``eval/`` scripts (which stay in ioc-core, referenced by
``IOC_REPO``). It consumes the traces an Experiment already produced (no MAS re-run) and:

  1. for each run: generate spans (``query_sweep/replay_events_to_spans.py``) and place the
     trace into a bundle via ``eval/build_bundle.py`` — tagging ``taxonomy_id`` (challenge
     code from the scenario) and ``probe_id`` (scenario), rep = per-scenario counter;
  2. name the bundle dir with the app's domain token (e.g. ``sre-triage``) so the evaluator
     routes the domain correctly;
  3. run ``eval/run_eval.sh`` (claris ``paper_v2``) → ``<out>/results/metrics_long.csv`` etc.

Config
------
ioc_repo       str  ioc-core-mas-lab checkout (default env IOC_REPO)   [required]
mas_lab_oss    str  OSS mas-lab checkout, for the venv python the span-converter needs
                    (default env MAS_LAB_OSS)                          [required]
claris_lib     str  claris-lib checkout (default env CLARIS_LIB)       [required]
evaluator_env  str  judge creds file (default env EVALUATOR_ENV or <ioc_repo>/.env.evaluator)
service_name   str  domain token for bundle naming / --service-name (e.g. "sre-triage") [required]
runs_dir       str  experiment trace root (default: ctx.output_dir)
suite / shards      eval suite (default paper_v2) / shard count (default 4)

NOTE (verify on first run): assumes each run dir contains ``events.jsonl`` and a
``run_info.json`` carrying the scenario. If the native layout differs, adjust
``_scenario_of`` / the glob below — this is the one interface not yet verified end-to-end.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput

if TYPE_CHECKING:
    from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)

_CODES = ("DR-1", "DC-2", "CC-3", "CR-1")  # priority challenge codes


def _code_of(scenario: str) -> str:
    """Map a scenario id to the eval's taxonomy_id (challenge code), or NONE for baseline."""
    s = (scenario or "").strip()
    if not s or s.lower().startswith(("baseline", "none")):
        return "NONE"
    for code in _CODES:
        if s.startswith(code):
            return code
    return "NONE"


def _scenario_of(run_dir: Path) -> str:
    """Best-effort scenario label for a run dir (run_info.json first, then path)."""
    info = run_dir / "run_info.json"
    if info.is_file():
        try:
            doc = json.loads(info.read_text(encoding="utf-8"))
            for k in ("scenario", "scenario_id", "probe_id", "config"):
                if doc.get(k):
                    return str(doc[k])
        except Exception:
            pass
    # fall back to the nearest path segment that names a scenario/overlay
    for part in reversed(run_dir.parts):
        if part.startswith(_CODES) or part.lower().startswith("baseline"):
            return part
    return run_dir.parent.name


def _event_counts(events_path: Path) -> tuple[int, int]:
    """(llm_call_start, tool_call_start) counts — mirrors the evaluator's eligibility filter."""
    llm = tool = 0
    try:
        with open(events_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"llm_call_start"' in line:
                    llm += 1
                elif '"tool_call_start"' in line:
                    tool += 1
    except OSError:
        pass
    return llm, tool


def _need(cfg: dict, key: str, env: str) -> Path:
    val = cfg.get(key) or os.environ.get(env, "")
    p = Path(val).expanduser()
    if not val or not p.exists():
        raise FileNotFoundError(f"ioc_cognitive_eval: {key}/{env} not set or missing: {val!r}")
    return p


class IocCognitiveEvalStep(PipelineStep):
    type = "ioc_cognitive_eval"
    persistent = True  # LLM-judge eval is expensive; cache the result

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        cfg = self.config
        ioc_repo = _need(cfg, "ioc_repo", "IOC_REPO")
        mas_oss = _need(cfg, "mas_lab_oss", "MAS_LAB_OSS")
        claris = _need(cfg, "claris_lib", "CLARIS_LIB")
        evaluator_env = Path(cfg.get("evaluator_env") or os.environ.get("EVALUATOR_ENV")
                             or (ioc_repo / ".env.evaluator")).expanduser()
        service = cfg.get("service_name")
        if not service:
            raise ValueError("ioc_cognitive_eval: config.service_name is required (domain token)")
        suite = cfg.get("suite", "paper_v2")
        shards = int(cfg.get("shards", 4))

        runs_dir = Path(cfg["runs_dir"]) if cfg.get("runs_dir") else ctx.output_dir
        out_dir = ctx.output_dir
        bundle = out_dir / service          # basename carries the domain token
        stage_root = out_dir / "_stage"
        oss_py = mas_oss / ".venv" / "bin" / "python"
        replay = ioc_repo / "query_sweep" / "replay_events_to_spans.py"
        build_bundle = ioc_repo / "eval" / "build_bundle.py"
        run_eval = ioc_repo / "eval" / "run_eval.sh"

        # Native run dirs symlink `traces/` into the content-addressed cache, so events.jsonl
        # live behind symlinks — Path.rglob won't follow them; os.walk(followlinks=True) does.
        # Prune our own output subdirs so a re-run can't rediscover staged/bundled copies.
        skip = {"_stage", "results", ".cache", service}
        event_files: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(runs_dir, followlinks=True):
            dirnames[:] = [d for d in dirnames if d not in skip]
            if "events.jsonl" in filenames:
                event_files.append(Path(dirpath) / "events.jsonl")
        event_files = sorted(set(event_files))
        if not event_files:
            raise FileNotFoundError(f"ioc_cognitive_eval: no events.jsonl under {runs_dir}")

        rep_counter: Dict[str, int] = defaultdict(int)
        built: List[str] = []
        skipped: List[str] = []
        for ev in event_files:
            run_dir = ev.parent.parent          # <run>/traces/events.jsonl -> <run>
            scenario = _scenario_of(run_dir)
            code = _code_of(scenario)

            # The evaluator's `select` requires >=1 llm_call_start AND >=1 tool_call_start
            # (require_tool_operations). Degenerate/failed native runs (e.g. one LLM call, no
            # tools) would be dropped there — but run_eval derives its --per-dataset quota from
            # the bundle size, so a bundle bigger than the eligible set makes `select` hard-fail
            # ("quota N exceeds eligible trajectories"). Skip such runs here so bundle == eligible.
            llm_n, tool_n = _event_counts(ev)
            if llm_n == 0 or tool_n == 0:
                skipped.append(f"{scenario} (llm={llm_n},tool={tool_n})")
                continue

            rep_counter[scenario] += 1
            rep = rep_counter[scenario]

            # Stage a real copy so spans are written outside the shared trace cache.
            stage = stage_root / f"{scenario}-r{rep}"
            stage.mkdir(parents=True, exist_ok=True)
            staged = stage / "events.jsonl"
            shutil.copy2(ev, staged)

            r1 = subprocess.run([str(oss_py), str(replay), str(staged),
                                 "--service-name", service, "--force"], capture_output=True, text=True)
            if r1.returncode != 0:
                logger.warning("replay failed for %s: %s", run_dir, r1.stderr[-400:]); continue
            r2 = subprocess.run(["python3", str(build_bundle), "--events", str(staged),
                                 "--taxonomy", code, "--bundle", str(bundle),
                                 "--probe-id", scenario, "--rep", str(rep)], capture_output=True, text=True)
            if r2.returncode != 0:
                logger.warning("build_bundle failed for %s: %s", run_dir, r2.stderr[-400:]); continue
            built.append(f"{scenario}/rep-{rep:02d}")

        if skipped:
            logger.warning("ioc_cognitive_eval: skipped %d degenerate/failed run(s) (no llm or "
                           "no tool ops, ineligible for the judge): %s", len(skipped), skipped)
        if not built:
            raise RuntimeError("ioc_cognitive_eval: no eligible traces (all runs had no tool "
                               "operations); check the experiment runs actually invoked tools")

        # Score exactly the eligible set we bundled: quota == bundle size == select's eligible set.
        r3 = subprocess.run(["bash", str(run_eval), "--bundle", str(bundle), "--out", str(out_dir),
                             "--env-file", str(evaluator_env), "--claris", str(claris),
                             "--suite", suite, "--shards", str(shards),
                             "--per-dataset", str(len(built))], text=True)
        results = out_dir / "results" / "metrics_long.csv"
        if r3.returncode != 0 or not results.is_file():
            raise RuntimeError(f"ioc_cognitive_eval: run_eval failed (rc={r3.returncode}); no metrics_long.csv")

        logger.info("ioc_cognitive_eval: built %d traces, results at %s", len(built), results)
        return StepOutput(
            data={"metrics_long": str(results),
                  "results_dir": str(out_dir / "results"),
                  "study_summary": str(out_dir / "results" / "study_summary.json"),
                  "bundle": str(bundle)},
            files=[results],
            metadata={"built": built, "skipped": skipped, "service_name": service},
        )

    def outputs_exist(self, output_dir: Path) -> bool:  # cache guard (expensive step)
        return (output_dir / "results" / "metrics_long.csv").exists()
