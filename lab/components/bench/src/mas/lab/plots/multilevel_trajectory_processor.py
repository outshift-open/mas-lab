#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""MultilevelTrajectoryPlotter — :class:`~mas.lab.processor.Processor` wrapper
for ``plot_multilevel_trajectory``.

Integrates the multilevel trajectory visualisation into the mas-lab processor
pipeline so it can be used as:

1. **Direct Python API**::

       from mas.lab.plots.multilevel_trajectory_processor import MultilevelTrajectoryPlotter
       from mas.lab.artifacts import Trajectory, PlotFile

       plotter = MultilevelTrajectoryPlotter()
       plot: PlotFile = plotter.process(Trajectory(path=Path("events.jsonl")))

2. **Pipeline step YAML**::

       - name: render-trajectory
         type: processor
         processor: multilevel-trajectory-plotter
         depends_on: [extract-trajectories]
         config:
           fmt: html
           width_mode: log
           output: "reports/multilevel.html"

3. **CLI shortcut**::

       mas-lab plot multilevel-trajectory runs/.../events.jsonl -o out.html

4. **Generic CLI**::

       mas-lab run processor multilevel-trajectory-plotter \\
           trace=runs/.../events.jsonl \\
           plot=out.html \\
           plot.format=html

The manifest YAML (``multilevel_trajectory_processor.yaml``) declares the named
slots so ``mas-lab run processor --list`` can describe the processor.
"""

from pathlib import Path
from typing import Any

from mas.lab.processor import Processor, register
from mas.lab.artifacts import Trajectory, PlotFile


@register
class MultilevelTrajectoryPlotter(Processor):
    """Render a multilevel MAS trajectory diagram (HTML or SVG).

    Accepts any :class:`~mas.lab.artifacts.Trajectory` or
    :class:`~mas.lab.artifacts.AnnotatedTrajectory` artifact and returns a
    :class:`~mas.lab.artifacts.PlotFile`.

    KWarg options
    -------------
    fmt : str
        ``"html"`` (interactive D3) or ``"svg"`` (static).  Default: ``"html"``.
    title : str
        Diagram title.  Default: ``"MAS Multilevel Trajectory"``.
    width_mode : str
        Column-width strategy: ``"fixed"`` | ``"proportional"`` | ``"log"``.
        Default: ``"log"``.
    show_user_actors : bool
        Render person-icon user nodes adjacent to session boundary states.
        Default: ``True``.
    output : str | Path, optional
        Write the rendered content to this path.  When not given the content
        is returned in-memory via ``PlotFile.data``.
    """

    name        = "multilevel-trajectory-plotter"
    input_kind  = "trajectory"
    output_kind = "plot_file"
    description = "Renders a multilevel MAS trajectory diagram (HTML or SVG)"
    priority    = 1

    def process(self, artifact: Any, **kwargs: Any) -> PlotFile:  # type: ignore[override]
        from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory

        # ── 1. Load events ─────────────────────────────────────────────────
        if isinstance(artifact, Trajectory):
            artifact.load()
            events = artifact.events
        elif isinstance(artifact, list):
            events = artifact
        elif isinstance(artifact, (str, Path)):
            from mas.lab.plots.trajectory import load_trace
            events = load_trace(artifact)
        else:
            raise TypeError(
                f"MultilevelTrajectoryPlotter: expected Trajectory, list[dict], "
                f"or path-like, got {type(artifact).__name__!r}"
            )

        # ── 2. Extract options ─────────────────────────────────────────────
        fmt              = str(kwargs.pop("fmt", kwargs.pop("format", "html"))).lower()
        title            = str(kwargs.pop("title", "MAS Multilevel Trajectory"))
        width_mode       = str(kwargs.pop("width_mode", "log"))
        show_user_actors = bool(kwargs.pop("show_user_actors", True))
        output_path_raw  = kwargs.pop("output", None)

        # ── 3. Render ──────────────────────────────────────────────────────
        rendered: str = plot_multilevel_trajectory(
            events,
            fmt=fmt,
            title=title,
            width_mode=width_mode,
            show_user_actors=show_user_actors,
        )

        # ── 4. Write to disk if requested ──────────────────────────────────
        out_path: Path | None = None
        if output_path_raw is not None:
            out_path = Path(output_path_raw)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered, encoding="utf-8")

        return PlotFile(
            path=out_path,
            data=rendered if out_path is None else None,
            format=fmt,
            meta={
                "title":       title,
                "width_mode":  width_mode,
                "source":      str(getattr(artifact, "path", "") or ""),
            },
        )

    def cli_options(self):  # type: ignore[override]
        return [
            {
                "param_decls": ["--format", "-f"],
                "type":        "choice",
                "choices":     ["html", "svg"],
                "default":     "html",
                "show_default": True,
                "help":        "Output format.",
            },
            {
                "param_decls": ["--title"],
                "default":     "MAS Multilevel Trajectory",
                "show_default": True,
                "help":        "Diagram title.",
            },
            {
                "param_decls": ["--width-mode"],
                "type":        "choice",
                "choices":     ["fixed", "proportional", "log"],
                "default":     "log",
                "show_default": True,
                "help":        "Column-width strategy.",
            },
            {
                "param_decls": ["--no-user-actors"],
                "is_flag":     True,
                "default":     False,
                "help":        "Suppress person-icon user nodes.",
            },
        ]
