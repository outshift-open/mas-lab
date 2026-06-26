#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Hand-drawn SVG renderer for trajectories (no external dependencies).

This processor always uses the native Python SVG renderer regardless of what
other renderers are available.  It is registered as ``trajectory_plotter_native``
and has ``priority=10`` (lower preference than the Mermaid-based renderer).

Use when:
- playwright / Chromium is not available
- Offline environments
- You need predictable, dependency-free SVG output
"""

from pathlib import Path
from typing import Any

from mas.lab.artifacts import PlotFile, Trajectory
from mas.lab.processor import Processor, register

_FORMATS = ("html", "svg", "svg_native", "mermaid", "table")


@register
class TrajectoryPlotterNative(Processor):
    """Render a Trajectory into a PlotFile using the hand-drawn SVG renderer.

    Identical interface to :class:`~mas.lab.processors.trajectory_plotter.TrajectoryPlotter`
    but always uses the native Python SVG renderer (``fmt="svg_native"``).
    ``format="svg"`` is silently remapped to ``"svg_native"`` so both work.

    Config / kwargs
    ---------------
    format : str
        Output format: ``html`` (default), ``svg`` / ``svg_native``, ``mermaid``, ``table``.
    output : Path, optional
        Destination file path.
    include_prompts : bool
        Show delegation task text on arrows (default: ``True``).
    highlights : list[str], optional
        Additional highlights.
    """

    name        = "trajectory_plotter_native"
    input_kind  = "trajectory"
    output_kind = "plot_file"
    description = "(Annotated)Trajectory  →  PlotFile — hand-drawn SVG (no playwright)"
    priority    = 10  # fallback renderer — prefer trajectory_plotter (priority=1)

    def process(
        self,
        artifact: Trajectory,
        format: str = "html",
        output: Path | str | None = None,
        include_prompts: bool = True,
        highlights: list[str] | None = None,
        **kwargs: Any,
    ) -> PlotFile:
        from mas.lab.plots.trajectory import plot_trajectory

        # Ensure events are loaded
        artifact.load()

        # Remap "svg" → "svg_native" so both spellings work
        fmt = "svg_native" if format == "svg" else format

        # Merge highlights from artifact + caller kwargs
        merged_highlights = list(getattr(artifact, "highlights", []))
        if highlights:
            merged_highlights = merged_highlights + list(highlights)

        content = plot_trajectory(
            artifact.events,
            fmt=fmt,
            include_prompts=include_prompts,
            highlights=merged_highlights or None,
        )

        # Resolve output path (use actual extension based on fmt)
        ext = "svg" if fmt in ("svg", "svg_native") else fmt
        if output is None and artifact.path:
            run_id = getattr(artifact, "run_id", None) or artifact.path.stem
            output = artifact.path.parent / f"{run_id}.{ext}"

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
                "param_decls": ["--no-prompts"],
                "is_flag": True,
                "default": False,
                "help": "Omit task/prompt text from diagram edges.",
            },
            {
                "param_decls": ["--highlight"],
                "multiple": True,
                "metavar": "CORR_OR_INDEX",
                "help": "Additional highlight (corr-id prefix or 1-based index).",
            },
        ]
