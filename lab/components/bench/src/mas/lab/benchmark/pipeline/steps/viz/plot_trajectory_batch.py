#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""PlotTrajectoryBatchStep — render trajectory diagrams for multiple runs in one step.

Config keys::

    runs: list         Required.  Each entry must have:
                           log_path: str   Path to events.jsonl for this run
                           filename: str   Output filename without extension
    format: str        Output format: mermaid (default), table, html.
    include_prompts: bool  Show full task text on diagram edges (default: true).
    concurrency: int   Max parallel renders (default: 1 = sequential).

Example pipeline YAML::

    - name: traj-all
      type: plot_trajectory_batch
      config:
        format: html
        include_prompts: true
        runs:
          - log_path: <labs_root>/.../baseline__item1__r1/traces/events.jsonl
            filename: trajectory-baseline
          - log_path: <labs_root>/.../full__item1__r1/traces/events.jsonl
            filename: trajectory-full
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from mas.lab.benchmark.pipeline import BatchPipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


class PlotTrajectoryBatchStep(BatchPipelineStep):
    """Render one trajectory diagram per run entry in a single pipeline step."""

    type = "plot_trajectory_batch"

    def _get_items(self, ctx: ExecutionContext) -> List[Dict[str, Any]]:
        runs = self.config.get("runs", [])
        if not runs:
            raise ValueError(
                f"Step '{self.name}': 'runs' list is required in config."
            )
        return runs

    async def process_one(self, item: Dict[str, Any], ctx: ExecutionContext) -> StepOutput:
        from mas.lab.plots.trajectory import load_trace, plot_trajectory

        log_path: str = item.get("log_path", "")
        filename: str = item.get("filename", "trajectory")
        fmt: str = self.config.get("format", "mermaid").lower()
        include_prompts: bool = self.config.get("include_prompts", True)

        if not log_path:
            raise ValueError(
                f"Step '{self.name}': each run entry must have a 'log_path'."
            )

        events = load_trace(log_path)
        logger.info("Step '%s': loaded %d events from %s", self.name, len(events), log_path)

        diagram = plot_trajectory(events, fmt=fmt, include_prompts=include_prompts)

        ext = {"mermaid": ".mmd", "table": ".txt", "html": ".html", "svg": ".svg"}.get(fmt, ".txt")
        output_dir = ctx.output_dir / "trajectories"
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{filename}{ext}"
        out_file.write_text(diagram, encoding="utf-8")

        logger.info("Step '%s': wrote %s (%d events)", self.name, out_file, len(events))

        return StepOutput(
            data={"trajectory_diagram": diagram, "format": fmt, "filename": filename},
            files=[out_file],
            metadata={"format": fmt, "events": len(events), "output_file": str(out_file)},
        )
