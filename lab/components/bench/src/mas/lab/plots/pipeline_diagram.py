#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Pipeline diagram renderer.

Produces a visual representation of a ``Pipeline`` (DAG of steps) in two
formats:

* ``"svg"``  — self-contained SVG string.  Embed in Markdown, HTML, or Jupyter
  notebooks via ``IPython.display.SVG``.
* ``"html"`` — self-contained dark HTML with D3-powered tooltips and hover
  highlighting.  Ideal for interactive Jupyter tutorials.

Public entry point::

    from mas.lab.plots.pipeline_diagram import plot_pipeline

    # From a Pipeline object (already loaded)
    svg = plot_pipeline(pipeline, fmt="svg")
    html = plot_pipeline(pipeline, fmt="html")

    # From a YAML path
    svg = plot_pipeline("pipeline-neo4j.yaml", fmt="svg")

    # In a notebook
    from IPython.display import HTML, SVG
    display(HTML(plot_pipeline("pipeline-neo4j.yaml", fmt="html")))
    display(SVG(plot_pipeline("pipeline-neo4j.yaml", fmt="svg")))

Design
------
Layout
    Topological left-to-right DAG.  Each step is assigned a *column* (rank =
    max(rank(dep) + 1)) and a *row* within that column.  Steps with no
    dependencies share column 0.

Rendering (SVG)
    Pure-Python string generation — no matplotlib, no external SVG library.
    Same dark-theme as ``multilevel_trajectory.py`` for visual consistency.

Rendering (HTML)
    Wraps the SVG in a minimal HTML page with vanilla-JS hover effects
    (highlight step + its edges on mouse-over).  No external CDN dependency.

Color coding
    Step type → family → accent colour (reuses ``mas.lab.plots.palette``):
    - graph (normalize, neo4j, validate, compare)  : petrol blue
    - experiment (dataset, experiment, analysis)   : green
    - eval (eval_mce, eval_adversarial, annotate_metrics)  : orange
    - embed (embed_*, compute_drift)               : violet
    - plot (plot_*, visualize_kg)                  : slate-teal
    - services (service_start, service_stop)       : sky blue
    - export (export_otel, list_*)                 : amber
    - unknown                                      : slate grey
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

__all__ = ["plot_pipeline"]


# ---------------------------------------------------------------------------
# Step-type → family mapping
# ---------------------------------------------------------------------------

_FAMILY: dict[str, str] = {}

def _reg(family: str, *types: str) -> None:
    for t in types:
        _FAMILY[t] = family

_reg("graph",
     "normalize_events", "normalize_events_batch", "normalize_otel",
     "normalize_observe", "events_to_otel",
     "neo4j_push", "neo4j_dump", "neo4j_annotate_metrics",
     "validate_kg", "compare_kg")
_reg("experiment",
     "dataset", "generate_dataset", "experiment",
     "extract_trajectories", "analysis")
_reg("eval",
     "eval_mce", "eval_batch", "eval_adversarial", "annotate_metrics")
_reg("embed",
     "embed_trajectories", "compute_drift")
_reg("plot",
     "plot", "plot_trajectory", "plot_trajectory_batch",
     "plot_multilevel_trajectory", "plot_multilevel_trajectory_batch",
     "plot_communication_flow", "visualize_kg")
_reg("services", "service_start", "service_stop")
_reg("export",
     "export_otel", "list_neo4j_sessions", "list_clickhouse_sessions")


# ---------------------------------------------------------------------------
# Dark-theme colours
# ---------------------------------------------------------------------------

_BG          = "#0f172a"
_CARD_BG     = "#1e293b"
_BORDER      = "#334155"
_TITLE_C     = "#f1f5f9"
_TEXT_C      = "#e2e8f0"
_SUB_C       = "#94a3b8"
_EDGE_C      = "#475569"
_ARROW_C     = "#64748b"
_EDGE_HL_C   = "#93c5fd"   # blue-300 — highlighted edge
_CARD_HL_C   = "#1d4ed8"   # blue-700 — highlighted card border

_FAMILY_ACCENT: dict[str, str] = {
    "graph":      "#0e7490",   # cyan-700
    "experiment": "#16a34a",   # green-600
    "eval":       "#ea580c",   # orange-600
    "embed":      "#7c3aed",   # violet-600
    "plot":       "#0891b2",   # cyan-600 (lighter)
    "services":   "#2563eb",   # blue-600
    "export":     "#d97706",   # amber-600
    "unknown":    "#64748b",   # slate-500
}

def _step_accent(step_type: str) -> str:
    return _FAMILY_ACCENT.get(_FAMILY.get(step_type, "unknown"), _FAMILY_ACCENT["unknown"])

def _family_label(step_type: str) -> str:
    return _FAMILY.get(step_type, "")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

@dataclass
class _Node:
    name: str
    step_type: str
    config: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    col: int = 0
    row: int = 0


def _compute_layout(steps: list[dict]) -> list[_Node]:
    """Assign (col, row) to each step via topological rank."""
    nodes: dict[str, _Node] = {}
    for s in steps:
        nodes[s["name"]] = _Node(
            name=s["name"],
            step_type=s.get("type", ""),
            config=s.get("config", {}),
            depends_on=s.get("depends_on", []),
        )

    # Compute column = rank
    rank: dict[str, int] = {}
    changed = True
    while changed:
        changed = False
        for name, node in nodes.items():
            r = max((rank.get(d, 0) + 1 for d in node.depends_on), default=0)
            if rank.get(name) != r:
                rank[name] = r
                changed = True

    for name, node in nodes.items():
        node.col = rank.get(name, 0)

    # Assign row within each column
    col_counters: dict[int, int] = {}
    for name, node in nodes.items():
        c = node.col
        node.row = col_counters.get(c, 0)
        col_counters[c] = node.row + 1

    return list(nodes.values())


# ---------------------------------------------------------------------------
# SVG constants
# ---------------------------------------------------------------------------

_CARD_W     = 160
_CARD_H     = 64
_COL_GAP    = 80    # horizontal gap between columns
_ROW_GAP    = 20    # vertical gap between rows in same column
_PAD_X      = 32
_PAD_Y      = 56    # space for title
_PAD_BOT    = 24
_ARROW_GAP  = 6     # gap between arrow tip and card edge
_RADIUS     = 8


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------------------
# SVG renderer
# ---------------------------------------------------------------------------

def _render_svg(nodes: list[_Node], title: str, highlight_id: str = "") -> str:
    """Render pipeline DAG as an SVG string."""
    if not nodes:
        return "<svg xmlns='http://www.w3.org/2000/svg'><text fill='white' y='20'>No steps</text></svg>"

    max_col = max(n.col for n in nodes)
    max_row_per_col: dict[int, int] = {}
    for n in nodes:
        max_row_per_col[n.col] = max(max_row_per_col.get(n.col, 0), n.row)

    max_rows = max(max_row_per_col.values()) + 1

    total_w = _PAD_X * 2 + (max_col + 1) * _CARD_W + max_col * _COL_GAP
    total_h = _PAD_Y + max_rows * _CARD_H + (max_rows - 1) * _ROW_GAP + _PAD_BOT

    # Center each column vertically within total height
    col_rows: dict[int, int] = {}
    for n in nodes:
        col_rows[n.col] = col_rows.get(n.col, 0) + 1

    def cx(col: int) -> float:
        return _PAD_X + col * (_CARD_W + _COL_GAP)

    def cy(col: int, row: int) -> float:
        n_rows = col_rows.get(col, 1)
        content_h = n_rows * _CARD_H + (n_rows - 1) * _ROW_GAP
        top_offset = (_PAD_Y + (total_h - _PAD_Y - _PAD_BOT - content_h) / 2)
        return top_offset + row * (_CARD_H + _ROW_GAP)

    # Build name → node map for edge lookup
    nmap: dict[str, _Node] = {n.name: n for n in nodes}

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" id="pipeline-diagram"',
        f' width="{total_w:.0f}" height="{total_h:.0f}"',
        f' viewBox="0 0 {total_w:.0f} {total_h:.0f}"',
        f' font-family="ui-monospace,SFMono-Regular,Consolas,monospace"',
        f' font-size="11">',
        f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="{_BG}"/>',
        '<defs>',
        f'<marker id="arr" markerWidth="6" markerHeight="5" refX="5.5" refY="2.5" orient="auto">',
        f'  <path d="M0,0 L6,2.5 L0,5 Z" fill="{_ARROW_C}"/></marker>',
        f'<marker id="arr-hl" markerWidth="6" markerHeight="5" refX="5.5" refY="2.5" orient="auto">',
        f'  <path d="M0,0 L6,2.5 L0,5 Z" fill="{_EDGE_HL_C}"/></marker>',
        '</defs>',
    ]

    # Title
    if title:
        parts.append(
            f'<text x="{_PAD_X}" y="{_PAD_Y - 16}"'
            f' font-size="14" font-weight="bold" fill="{_TITLE_C}">{_esc(title)}</text>'
        )

    # Edges (drawn first, behind cards)
    for node in nodes:
        x1_right = cx(node.col) + _CARD_W
        y1_mid = cy(node.col, node.row) + _CARD_H / 2
        for dep in node.depends_on:
            dep_node = nmap.get(dep)
            if dep_node is None:
                continue
            x0_right = cx(dep_node.col) + _CARD_W
            y0_mid = cy(dep_node.col, dep_node.row) + _CARD_H / 2

            # Simple horizontal + vertical path
            mid_x = x0_right + _COL_GAP / 2

            hl = highlight_id in (node.name, dep)
            edge_c = _EDGE_HL_C if hl else _EDGE_C
            marker = "arr-hl" if hl else "arr"
            stroke_w = "2" if hl else "1.5"

            parts.append(
                f'<path d="M{x0_right:.0f},{y0_mid:.0f}'
                f' H{mid_x:.0f}'
                f' V{y1_mid:.0f}'
                f' H{x1_right - _ARROW_GAP:.0f}"'
                f' stroke="{edge_c}" stroke-width="{stroke_w}"'
                f' fill="none" marker-end="url(#{marker})"'
                f' class="edge" data-from="{_esc(dep)}" data-to="{_esc(node.name)}"/>'
            )

    # Cards
    for node in nodes:
        x = cx(node.col)
        y = cy(node.col, node.row)
        accent = _step_accent(node.step_type)
        family = _family_label(node.step_type)

        # Shortened display name
        display_type = node.step_type.replace("_", "\u200b_")  # allow wrap at _

        # Config summary (first 2 non-empty entries)
        config_items = [f"{k}: {v}" for k, v in (node.config or {}).items() if v != ""]
        config_summary = " · ".join(config_items[:2])
        if len(config_items) > 2:
            config_summary += " …"

        parts.append(
            f'<g class="step-card" data-name="{_esc(node.name)}">'
        )
        # Card background
        parts.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{_CARD_W}" height="{_CARD_H}"'
            f' rx="{_RADIUS}" fill="{_CARD_BG}" stroke="{accent}" stroke-width="2"/>'
        )
        # Left accent bar
        parts.append(
            f'<rect x="{x:.0f}" y="{y:.0f}" width="4" height="{_CARD_H}"'
            f' rx="{_RADIUS}" fill="{accent}"/>'
        )
        # Step name
        parts.append(
            f'<text x="{x + 12:.0f}" y="{y + 20:.0f}"'
            f' font-size="11" font-weight="bold" fill="{_TEXT_C}"'
            f' clip-path="url(#clip-{_esc(node.name)})">'
            f'{_esc(node.name)}</text>'
        )
        # Step type
        parts.append(
            f'<text x="{x + 12:.0f}" y="{y + 36:.0f}"'
            f' font-size="10" fill="{accent}">'
            f'{_esc(node.step_type)}</text>'
        )
        # Config summary
        if config_summary:
            parts.append(
                f'<text x="{x + 12:.0f}" y="{y + 52:.0f}"'
                f' font-size="9" fill="{_SUB_C}">'
                f'{_esc(config_summary[:30])}{"…" if len(config_summary) > 30 else ""}'
                f'</text>'
            )
        parts.append('</g>')

    parts.append('</svg>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML wrapper (interactive)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ margin: 0; background: {bg}; display: flex; justify-content: center; }}
  #pipeline-diagram {{ display: block; max-width: 100%; }}
  .step-card {{ cursor: pointer; }}
  .step-card:hover rect:first-of-type {{ stroke-width: 3; }}
  .edge {{ transition: stroke 0.15s; }}
</style>
</head>
<body>
{svg}
<script>
(function() {{
  const svg = document.getElementById('pipeline-diagram');
  if (!svg) return;

  const cards = svg.querySelectorAll('.step-card');
  const edges = svg.querySelectorAll('.edge');

  const EDGE_C   = '{edge_c}';
  const EDGE_HL  = '{edge_hl}';
  const ARROW_C  = '{arrow_c}';

  function setEdgeColor(edge, hl) {{
    edge.setAttribute('stroke', hl ? EDGE_HL : EDGE_C);
    edge.setAttribute('marker-end', hl ? 'url(#arr-hl)' : 'url(#arr)');
    edge.setAttribute('stroke-width', hl ? '2' : '1.5');
  }}

  function resetAll() {{
    edges.forEach(e => setEdgeColor(e, false));
  }}

  cards.forEach(card => {{
    const name = card.dataset.name;
    card.addEventListener('mouseenter', () => {{
      resetAll();
      edges.forEach(e => {{
        if (e.dataset.from === name || e.dataset.to === name) {{
          setEdgeColor(e, true);
        }}
      }});
    }});
    card.addEventListener('mouseleave', resetAll);
  }});
}})();
</script>
</body>
</html>
"""


def _fmt_html(svg: str, title: str) -> str:
    return _HTML_TEMPLATE.format(
        title=title or "Pipeline",
        bg=_BG,
        svg=svg,
        edge_c=_EDGE_C,
        edge_hl=_EDGE_HL_C,
        arrow_c=_ARROW_C,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def plot_pipeline(
    pipeline: "Union[str, Path, dict, Any]",
    fmt: str = "html",
    title: str | None = None,
) -> str:
    """Render a pipeline DAG as SVG or interactive HTML.

    Parameters
    ----------
    pipeline:
        One of:
        - A ``Pipeline`` object (from ``mas.lab.benchmark.pipeline``).
        - A ``str`` or ``Path`` to a pipeline YAML file.
        - A ``dict`` with a ``steps`` key (raw YAML data).
    fmt:
        ``"html"`` (default) — self-contained HTML with hover interactions.
        ``"svg"``  — raw SVG string.
    title:
        Override the diagram title.  If omitted, uses the pipeline name.

    Returns
    -------
    str
        SVG string or full HTML page, ready to write to a file or display
        in a notebook::

            from IPython.display import HTML, SVG
            display(HTML(plot_pipeline("pipeline-neo4j.yaml", fmt="html")))
            display(SVG(plot_pipeline("pipeline-neo4j.yaml", fmt="svg")))
    """
    steps, name = _load_pipeline(pipeline)
    _title = title or name or "Pipeline"
    nodes = _compute_layout(steps)
    svg = _render_svg(nodes, _title)
    if fmt == "svg":
        return svg
    if fmt == "html":
        return _fmt_html(svg, _title)
    raise ValueError(f"Unknown format '{fmt}'. Use: svg, html")


# ---------------------------------------------------------------------------
# Pipeline loader
# ---------------------------------------------------------------------------

def _load_pipeline(pipeline: Any) -> tuple[list[dict], str]:
    """Return (list_of_step_dicts, pipeline_name) from any input form."""
    # Already a Pipeline object from mas.lab.benchmark.pipeline
    if hasattr(pipeline, "steps") and hasattr(pipeline, "config"):
        steps = [
            {
                "name": s.name,
                "type": getattr(s, "type", ""),
                "config": getattr(s, "config", {}),
                "depends_on": getattr(s, "depends_on", []),
            }
            for s in pipeline.steps
        ]
        name = getattr(pipeline.config, "name", "pipeline")
        return steps, name

    # Path or string → load YAML
    if isinstance(pipeline, (str, Path)):
        from mas.lab.manifests.loader import load_pipeline_data

        data, _ = load_pipeline_data(Path(pipeline))
        return _load_pipeline(data)

    # dict
    if isinstance(pipeline, dict):
        # Manifest format: api_version / kind / spec
        if "spec" in pipeline:
            spec = pipeline["spec"]
            meta = pipeline.get("metadata", {})
            name = meta.get("name", pipeline.get("name", "pipeline"))
            return spec.get("steps", []), name
        # Experiment format: experiment.run.pipeline (+ optional experiment.experiment.pipeline)
        if "experiment" in pipeline:
            inner = pipeline["experiment"]
            name = inner.get("name", "experiment")
            run_steps = inner.get("run", {}).get("pipeline", []) or []
            exp_steps = inner.get("experiment", {}).get("pipeline", []) or []
            return run_steps + exp_steps, name
        # Legacy flat format
        inner = pipeline.get("pipeline", pipeline)
        return inner.get("steps", []), inner.get("name", "pipeline")

    raise TypeError(f"Cannot load pipeline from {type(pipeline)}")
