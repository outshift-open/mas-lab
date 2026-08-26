#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ioc_delta — baseline-vs-overlay delta/verdict step.

Thin adapter over ioc-core's ``eval/delta_report.py --json`` (the single source of
truth; it stays in ioc-core and is referenced by ``IOC_REPO``). Consumes the
``metrics_long.csv`` produced by the upstream ``ioc_cognitive_eval`` step and emits:

  * ``report.json``          — {baseline, challenges[{verdict, footprint, per_metric}], confidence}
                               (the same shape the IoC results page renders)
  * ``ablation_matrix.json`` — list[{challenge, metric, delta}] flattened from the report,
                               ready for the native ``plot`` step + ``ablation_heatmap`` spec
                               (paper Fig 4).

Config
------
ioc_repo       str  path to the ioc-core-mas-lab checkout (default: env IOC_REPO)
metrics_long   str  path to metrics_long.csv (default: from the upstream step's output,
                    else ``<ctx.output_dir>/results/metrics_long.csv``)
depends_on     the cognitive-eval step, so its output is in ctx.step_outputs.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput

if TYPE_CHECKING:
    from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


class IocDeltaStep(PipelineStep):
    type = "ioc_delta"

    def _resolve_metrics_long(self, ctx: "ExecutionContext") -> Path:
        cfg = self.config
        if cfg.get("metrics_long"):
            return Path(cfg["metrics_long"])
        # prefer an upstream ioc_cognitive_eval step's declared output
        for dep_out in ctx.step_outputs.values():
            ml = (getattr(dep_out, "data", {}) or {}).get("metrics_long")
            if ml:
                return Path(ml)
        return ctx.output_dir / "results" / "metrics_long.csv"

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        cfg = self.config
        ioc_repo = Path(cfg.get("ioc_repo") or os.environ.get("IOC_REPO", "")).expanduser()
        if not ioc_repo or not ioc_repo.is_dir():
            raise FileNotFoundError(
                f"ioc_delta: IOC_REPO not set / not a dir: {ioc_repo!r} "
                "(point it at the ioc-core-mas-lab checkout)"
            )
        delta_report = ioc_repo / "eval" / "delta_report.py"
        metrics_long = self._resolve_metrics_long(ctx)
        if not metrics_long.is_file():
            raise FileNotFoundError(f"ioc_delta: metrics_long.csv not found: {metrics_long}")

        proc = subprocess.run(
            ["python3", str(delta_report), str(metrics_long), "--json"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ioc_delta: delta_report failed (rc={proc.returncode})\n{proc.stderr}")
        report: Dict[str, Any] = json.loads(proc.stdout)

        # Flatten challenges[].per_metric[] -> ablation_matrix for the native heatmap.
        ablation_matrix: List[Dict[str, Any]] = [
            {"challenge": ch.get("code") or ch.get("scenario"), "metric": pm["metric"], "delta": pm["delta"]}
            for ch in report.get("challenges", [])
            for pm in ch.get("per_metric", [])
            if pm.get("delta") is not None
        ]

        out = ctx.output_dir
        out.mkdir(parents=True, exist_ok=True)
        report_path = out / "report.json"
        matrix_path = out / "ablation_matrix.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        matrix_path.write_text(json.dumps(ablation_matrix, indent=2), encoding="utf-8")

        reproduced = [c["code"] for c in report.get("challenges", []) if c.get("verdict") == "reproduced"]
        logger.info("ioc_delta: %d challenges, reproduced on intended metric: %s",
                    len(report.get("challenges", [])), reproduced or "none")

        return StepOutput(
            data={"report": report, "ablation_matrix": ablation_matrix,
                  "report_path": str(report_path), "ablation_matrix_path": str(matrix_path)},
            files=[report_path, matrix_path],
            metadata={"reproduced": reproduced, "reps": report.get("reps")},
        )

    def outputs_exist(self, output_dir: Path) -> bool:  # cache guard
        return (output_dir / "report.json").exists()
