#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Render a :class:`~mas.lab.artifacts.Trajectory` into a plot file."""

from pathlib import Path
from typing import Any

from mas.lab.artifacts import PlotFile, Trajectory
from mas.lab.processor import Processor, register

_FORMATS = ("html", "svg", "svg_native", "mermaid", "md", "table")


@register
class TrajectoryPlotter(Processor):
    """Render a (optionally annotated) Trajectory into a PlotFile.

    SVG output uses Mermaid rendered via headless Chromium (playwright) — the
    diagram is identical to the HTML output and preserves the full delegation
    chain.  Falls back transparently to the hand-drawn native SVG renderer if
    playwright is unavailable.

    Use ``format="svg_native"`` to force the hand-drawn renderer directly, or
    use the :class:`TrajectoryPlotterNative` processor (``trajectory_plotter_native``).

    Config / kwargs
    ---------------
    format : str
        Output format: ``html`` (default), ``svg``, ``svg_native``, ``mermaid``,
        ``md`` (Mermaid fenced block for Markdown documents), ``table``.
    output : Path, optional
        Destination file path.  Defaults to a ``trajectory.<format>`` sibling
        of the input trace file if available.  For ``format="md"`` the extension
        is ``.md``.
    title : str, optional
        Heading prepended to ``format="md"`` output.  Defaults to the run_id.
    include_prompts : bool
        Show delegation task text on arrows (default: ``True``).
    highlights : list[str], optional
        Additional highlights on top of those already on the artifact.

    Examples
    --------
    ::

        plotter = TrajectoryPlotter()
        plot = plotter.process(annotated_traj, format="svg", output=Path("/tmp/out.svg"))
        md   = plotter.process(traj, format="md",  title="Scenario: baseline")
    """

    name        = "trajectory_plotter"
    input_kind  = "trajectory"          # also accepts annotated_trajectory
    output_kind = "plot_file"
    description = "(Annotated)Trajectory  →  PlotFile (html|svg|mermaid|md)"
    priority    = 1  # preferred SVG renderer (Mermaid via playwright)

    def process(
        self,
        artifact: Trajectory,
        format: str = "html",
        output: Path | str | None = None,
        title: str | None = None,
        include_prompts: bool = True,
        highlights: list[str] | None = None,
        **kwargs: Any,
    ) -> PlotFile:
        from mas.lab.plots.trajectory import plot_trajectory

        # Ensure events are loaded
        artifact.load()

        # Merge highlights from artifact + caller kwargs
        merged_highlights = list(getattr(artifact, "highlights", []))
        if highlights:
            merged_highlights = merged_highlights + list(highlights)

        # Default title from run_id for md format
        if format == "md" and title is None:
            title = getattr(artifact, "run_id", None) or (artifact.path.stem if artifact.path else None)

        content = plot_trajectory(
            artifact.events,
            fmt=format,
            include_prompts=include_prompts,
            highlights=merged_highlights or None,
            title=title,
        )

        # Resolve output path — md format uses .md extension
        if output is None and artifact.path:
            run_id = getattr(artifact, "run_id", None) or artifact.path.stem
            ext = "md" if format == "md" else format
            output = artifact.path.parent / f"{run_id}.{ext}"

        if output is not None:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            return PlotFile(path=out_path, format=format)

        # No path — return in-memory (data field)
        return PlotFile(data=content, format=format)

    def cli_options(self):
        return [
            {
                "param_decls": ["--format", "-f"],
                "type": "choice",
                "choices": _FORMATS,
                "default": "html",
                "show_default": True,
                "help": "Output format (html/svg/svg_native/mermaid/md/table).",
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
