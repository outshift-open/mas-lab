#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""PlotTrajectoryStep — pipeline step that renders an agent trajectory diagram.

Config keys::

    log_path: str      Path to a .jsonl trace file OR a run_id string.
                       If omitted, the step looks for trace files produced by
                       a dependency step (key "trace_path" in StepOutput.data).
    format: str        Output format: mermaid (default), table, html.
    include_prompts: bool  Show full task text on diagram edges (default: true).
    filename: str      Output filename without extension (default: "trajectory").

Example pipeline YAML::

    - name: traj
      type: plot_trajectory
      depends_on: [run]
      config:
        format: html
        include_prompts: true
"""

import logging
from pathlib import Path
from typing import Any, Dict

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


class PlotTrajectoryStep(PipelineStep):
    """Generate an agent trajectory diagram from a MAS trace."""

    type = "plot_trajectory"

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        """Render trajectory diagram.

        Config:
            log_path (str): Path or run_id. Falls back to ``trace_path`` in
                dependency output.
            format (str): mermaid | table | html  (default: mermaid)
            include_prompts (bool): Show task text on edges (default: true)
            filename (str): Base name for output file (default: trajectory)
        """
        from mas.lab.plots.trajectory import load_trace, plot_trajectory

        config = self.config
        fmt = config.get("format", "mermaid").lower()
        include_prompts = config.get("include_prompts", True)
        filename = config.get("filename", "trajectory")
        highlight_agents   = config.get("highlight_agents")  or None
        highlight_keywords = config.get("highlight_keywords") or None

        # --- Resolve trace source ---
        # Preference: explicit config > kg_path from dependency > trace_path.
        log_path: str | None = config.get("log_path")

        if not log_path:
            for dep_name in self.depends_on:
                dep_out = ctx.step_outputs.get(dep_name)
                if dep_out:
                    for key in ("kg_path", "normalized_trace_path", "trace_path"):
                        if key in dep_out.data:
                            log_path = dep_out.data[key]
                            logger.info(
                                "Step '%s': using %s from dependency '%s': %s",
                                self.name, key, dep_name, log_path,
                            )
                            break
                if log_path:
                    break

        if not log_path:
            raise ValueError(
                f"Step '{self.name}': no log_path in config and no 'trace_path' "
                "found in dependency outputs."
            )

        # --- Resolve log_path ---
        # Relative paths are resolved first against the pipeline yaml's parent,
        # then against CWD — so pipeline.yaml and trace files can use the same
        # workspace-relative paths regardless of which directory the CLI is run from.
        resolved_path = Path(log_path).expanduser()
        if not resolved_path.is_absolute():
            pipeline_dir = (ctx.pipeline.config_path.parent
                            if ctx.pipeline.config_path else Path.cwd())
            candidate = (pipeline_dir / resolved_path).resolve()
            if candidate.exists():
                resolved_path = candidate
            else:
                resolved_path = (Path.cwd() / resolved_path).resolve()

        # --- Load & render ---
        events = load_trace(resolved_path)
        logger.info("Step '%s': loaded %d events from %s", self.name, len(events), log_path)

        diagram = plot_trajectory(
            events,
            fmt=fmt,
            include_prompts=include_prompts,
            highlight_agents=highlight_agents,
            highlight_keywords=highlight_keywords,
        )

        # --- Write output file ---
        ext = {"mermaid": ".mmd", "table": ".txt", "html": ".html", "svg": ".svg"}.get(fmt, ".txt")
        output_dir = ctx.output_dir / "trajectories"
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{filename}{ext}"
        out_file.write_text(diagram, encoding="utf-8")

        logger.info("Step '%s': wrote %s (%d events, %d chars)",
                    self.name, out_file, len(events), len(diagram))

        return StepOutput(
            data={"trajectory_diagram": diagram, "format": fmt},
            files=[out_file],
            metadata={
                "format": fmt,
                "events": len(events),
                "output_file": str(out_file),
            },
        )
