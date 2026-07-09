#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""PlotCommunicationFlowStep — pipeline step for the communication-flow diagram.

Wraps :func:`~mas.lab.plots.communication_flow.plot_communication_flow`
so it can be declared declaratively in a ``pipeline/v1`` YAML manifest.

Config keys::

    log_path : str
        Path to a ``events.jsonl`` trace file.
        If omitted the step resolves ``kg_path`` or ``trace_path``
        from a dependency step's output data.
    format : str
        Output format: ``html`` (default, interactive D3) or ``mermaid``.
    title : str
        Diagram title (default: "MAS Agent Communication Flow").
    filename : str
        Output filename without extension (default: ``communication_flow``).

Example pipeline YAML::

    - name: flow-item1
      type: plot_communication_flow
      depends_on: [normalize-item1]
      config:
        format: html
        title: "Trip Planner — Agent Communication Flow (item 1)"
        filename: flow-item1
"""

import logging
from pathlib import Path

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


class PlotCommunicationFlowStep(PipelineStep):
    """Generate an agent communication-flow diagram from a trace."""

    type = "plot_communication_flow"

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        from mas.lab.plots.trajectory import load_trace
        from mas.lab.plots.communication_flow import plot_communication_flow

        config = self.config
        fmt = str(config.get("format", "html")).lower()
        title = str(config.get("title", "MAS Agent Communication Flow"))
        filename = str(config.get("filename", "communication_flow"))

        pipeline_dir: Path | None = (
            ctx.pipeline.config_path.parent
            if ctx.pipeline is not None and getattr(ctx.pipeline, "config_path", None)
            else None
        )

        # Resolve trace source: explicit config > kg_path from dep > trace_path
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
                f"Step '{self.name}': no log_path in config and no trace_path "
                "found in dependency outputs."
            )

        resolved_path = Path(log_path).expanduser()
        if not resolved_path.is_absolute() and pipeline_dir:
            candidate = (pipeline_dir / resolved_path).resolve()
            resolved_path = candidate if candidate.exists() else (Path.cwd() / resolved_path).resolve()
        elif not resolved_path.is_absolute():
            resolved_path = (Path.cwd() / resolved_path).resolve()

        events = load_trace(resolved_path)
        logger.info("Step '%s': loaded %d events from %s", self.name, len(events), resolved_path)

        rendered = plot_communication_flow(events, fmt=fmt, title=title)

        ext = ".html" if fmt == "html" else ".mermaid"
        output_dir = ctx.output_dir / "flows"
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{filename}{ext}"
        out_file.write_text(rendered, encoding="utf-8")

        logger.info("Step '%s': wrote %s (%d chars)", self.name, out_file, len(rendered))

        return StepOutput(
            data={"communication_flow": rendered, "format": fmt, "filename": filename},
            files=[out_file],
            metadata={
                "format": fmt,
                "events": len(events),
                "output_file": str(out_file),
                "title": title,
            },
        )
