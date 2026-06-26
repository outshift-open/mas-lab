#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Pipeline processor for message-graph plots."""

from pathlib import Path
from typing import Any

from mas.lab.artifacts import PlotFile, Trajectory
from mas.lab.processor import Processor, register
from mas.lab.plots.message_graph.plot import plot_message_graph

# ---------------------------------------------------------------------------
# Processor integration
# ---------------------------------------------------------------------------


@register
class MessageGraphPlotter(Processor):
    """Render a whole-run agent message-flow diagram (SVG or HTML).

    Accepts a :class:`~mas.lab.artifacts.Trajectory` and returns a
    :class:`~mas.lab.artifacts.PlotFile`.

    KWarg options
    -------------
    fmt : str
        ``"svg"`` (default) or ``"html"``.
    title : str
        Diagram title.  Default: run_id extracted from kg metadata.
    output : str | Path, optional
        Write output to this path.  When absent, content is returned in-memory.
    """

    name        = "message-graph-plotter"
    input_kind  = "trajectory"
    output_kind = "plot_file"
    description = "Renders a whole-run agent message-flow swimlane diagram (SVG/HTML)"
    priority    = 1

    def process(self, artifact: Any, **kwargs: Any) -> PlotFile:  # type: ignore[override]
        from mas.lab.plots.kg_adapter import load_kg

        fmt: str   = kwargs.get("fmt", "svg").lower()
        title: str = kwargs.get("title", "")
        output: Path | None = Path(kwargs["output"]) if kwargs.get("output") else None

        # ── resolve input path ────────────────────────────────────────────
        if isinstance(artifact, Trajectory):
            kg_path = artifact.path
            if kg_path is None or not Path(kg_path).exists():
                from mas.lab import paths as _paths
                kg_path = _paths.resolve_run_artifact(
                    str(artifact.run_id), artifact="kg.json"
                )
        else:
            kg_path = Path(str(artifact))

        kg = load_kg(kg_path)
        if not title:
            title = kg.get("run_id") or kg.get("meta", {}).get("run_id") or ""

        content = plot_message_graph(kg, title=title, fmt=fmt)

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding="utf-8")

        return PlotFile(data=content, path=output, format=fmt)
