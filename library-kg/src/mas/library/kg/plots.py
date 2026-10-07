#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""KG-driven plots — multilevel trajectory swim-lane rendering from a KG.

"Plots leveraging the KG and ontology live in library-kg." This module owns the
KG-specific plotting surface: a ``PipelineStep`` (``plot_multilevel_trajectory_kg``)
and a ``Processor`` (``multilevel_trajectory_kg_plotter``) that turn a ``kg.jsonld``
into a multilevel swim-lane diagram.

The generic swim-lane *renderer* (``plot_multilevel_trajectory_from_kg``) and the
``KGSource`` adapter are reused from ``mas.lab.plots`` for now; internalising the
renderer into library-kg (dropping the ``mas.lab.plots`` dependency) is a
follow-up. Requires the ``[plot]`` extra (bench framework + mas-lab plotting).

Imports are at module top so any import problem surfaces when the step/processor
is resolved at startup — never mid-render.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mas.lab.artifacts import KnowledgeGraph, PlotFile
from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.plots.kg_adapter import KGSource
from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory_from_kg
from mas.lab.processor import Processor

if TYPE_CHECKING:
    from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["MultilevelTrajectoryKGPlotter", "PlotMultilevelTrajectoryKGStep"]

_FORMATS = ("html", "svg")


class MultilevelTrajectoryKGPlotter(Processor):
    """Render a ``KnowledgeGraph`` artifact into a multilevel swim-lane ``PlotFile``."""

    name = "multilevel_trajectory_kg_plotter"
    input_kind = "knowledge_graph"
    output_kind = "plot_file"
    description = "KnowledgeGraph → multilevel swim-lane PlotFile (KG adapter)"
    priority = 5

    def process(
        self,
        artifact: KnowledgeGraph,
        format: str = "html",
        output: "Path | str | None" = None,
        title: str = "MAS Multilevel Trajectory",
        width_mode: str = "log",
        show_provenance: bool = True,
        **kwargs: Any,
    ) -> PlotFile:
        fmt = format.lower()
        kg_data = artifact.load_json() if artifact.path else artifact.data
        content = plot_multilevel_trajectory_from_kg(
            KGSource(kg_data),
            fmt=fmt,
            title=title,
            width_mode=width_mode,
            show_provenance=show_provenance,
        )
        if output is None and artifact.path:
            output = artifact.path.parent / "trajectory-kg.html"
        if output is not None:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            return PlotFile(path=out_path, format=fmt)
        return PlotFile(data=content, format=fmt)

    def cli_options(self):
        return [
            {
                "param_decls": ["--format", "-f"],
                "type": "choice",
                "choices": _FORMATS,
                "default": "html",
                "show_default": True,
                "help": "Output format.",
            },
            {
                "param_decls": ["--title"],
                "default": "MAS Multilevel Trajectory",
                "help": "Diagram title.",
            },
        ]


class PlotMultilevelTrajectoryKGStep(PipelineStep):
    """Pipeline step: ``kg.jsonld`` → multilevel swim-lane diagram."""

    type = "plot_multilevel_trajectory_kg"

    async def execute(self, ctx: "ExecutionContext") -> "StepOutput":
        config = self.config
        fail_on_error = bool(config.get("fail_on_error", True))
        try:
            return await self._execute(ctx, config)
        except Exception as exc:
            if fail_on_error:
                raise
            logger.warning("Step '%s': skipped due to error: %s", self.name, exc)
            return StepOutput(
                data={"skipped": True, "error": str(exc)}, files=[], metadata={}
            )

    async def _execute(self, ctx: "ExecutionContext", config: dict) -> "StepOutput":
        kg_path = config.get("kg_path")
        if not kg_path:
            for dep_name in self.depends_on:
                out = ctx.step_outputs.get(dep_name)
                if out and "kg_path" in out.data:
                    kg_path = out.data["kg_path"]
                    break
        if not kg_path or not Path(kg_path).exists():
            raise FileNotFoundError(
                f"Step '{self.name}': kg.jsonld not found ({kg_path})"
            )

        fmt = str(config.get("format", "html")).lower()
        content = plot_multilevel_trajectory_from_kg(
            KGSource.from_file(kg_path),
            fmt=fmt,
            title=str(config.get("title", "MAS Multilevel Trajectory")),
            width_mode=str(config.get("width_mode", "log")),
            show_provenance=bool(config.get("show_provenance", True)),
        )
        output_dir = ctx.get_step_output_dir(self.name)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"trajectory-kg.{fmt}"
        out_path.write_text(content, encoding="utf-8")
        return StepOutput(
            data={"plot_path": str(out_path), "format": fmt, "kg_path": str(kg_path)},
            files=[out_path],
            metadata={"step": self.name, "step_type": self.type},
        )
