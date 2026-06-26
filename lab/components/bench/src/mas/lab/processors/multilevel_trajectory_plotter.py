#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Processor: multilevel trajectory plotter.

Registered as ``multilevel_trajectory_plotter``.

Produces a multilevel HTML/SVG diagram showing Session → MAS → Agent → Call
swim lanes from a raw MAS event trace.  No external dependencies required.

Config / kwargs
---------------
format : str
    ``"html"`` (default) or ``"svg"``.
output : Path, optional
    Destination file path.
title : str, optional
    Diagram title.
"""

from pathlib import Path
from typing import Any

from mas.lab.artifacts import PlotFile, Trajectory
from mas.lab.processor import Processor, register

_FORMATS = ("html", "svg")


@register
class MultilevelTrajectoryPlotter(Processor):
    """Render a Trajectory into a multilevel swim-lane PlotFile.

    Produces four stacked swim lanes (Session / MAS / Agent / Call) with
    shared state circles, colored transitions, and JS hover tooltips.

    No external dependencies — pure Python SVG generation.

    Config / kwargs
    ---------------
    format : str
        ``"html"`` (default) or ``"svg"``.
    output : Path, optional
        Destination file path.
    title : str, optional
        Diagram title (default: «MAS Multilevel Trajectory»).
    """

    name        = "multilevel_trajectory_plotter"
    input_kind  = "trajectory"
    output_kind = "plot_file"
    description = "Trajectory → multilevel swim-lane PlotFile (Session/MAS/Agent/Call)"
    priority    = 5   # between trajectory_plotter (1) and trajectory_plotter_native (10)

    def process(
        self,
        artifact: Trajectory,
        format: str = "html",
        output: "Path | str | None" = None,
        title: str = "MAS Multilevel Trajectory",
        **kwargs: Any,
    ) -> PlotFile:
        from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory

        artifact.load()

        fmt = format.lower()
        content = plot_multilevel_trajectory(artifact.events, fmt=fmt, title=title)

        ext = fmt
        if output is None and artifact.path:
            run_id = getattr(artifact, "run_id", None) or artifact.path.stem
            output = artifact.path.parent / f"{run_id}_multilevel.{ext}"

        if output is not None:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            return PlotFile(path=out_path, format=ext)

        return PlotFile(data=content, format=ext)

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
