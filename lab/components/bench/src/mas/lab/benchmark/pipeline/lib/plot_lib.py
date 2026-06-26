#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Plot library for the MAS pipeline.

Declarative, grammar-of-graphics–inspired plot system.

Each plot is defined by a YAML spec in ``plot_library/`` (same directory as
this module).  The spec describes data mappings, marks, scales, aesthetics,
and layout in a format independent of any specific Python library.

Usage
-----
.. code-block:: yaml

    - name: my-plot
      type: plot
      depends_on: [my-analysis]
      config:
        spec: shapley_bars           # name of YAML in plot_library/
        data_key: scores          # optional override of spec's data.key
        params:
          title: "My custom title"

Or load a spec directly in Python:

.. code-block:: python

    from mas.lab.benchmark.pipeline.lib.plot_lib import PlotRegistry, render_plot

    spec = PlotRegistry.load("shapley_bars")
    output_path = render_plot(spec, data=my_scores_list, output_dir=Path("./plots"))

Extending
---------
To add a new plot type:
1. Add a YAML spec to ``plot_library/<name>.yaml``
2. Implement a ``_render_<type>`` function in this module (or a plugin file)
3. Register it in ``_RENDERERS``

The spec schema is documented in each YAML file and summarised in the
``PlotSpec`` dataclass below.
"""

import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Spec data model
# ---------------------------------------------------------------------------

_PLOT_LIBRARY_DIR = Path(__file__).parent / "plot_specs"


@dataclass
class PlotSpec:
    """In-memory representation of a plot YAML spec."""

    name: str
    plot_type: str
    title: str = ""
    subtitle: str = ""
    description: str = ""

    data: Dict[str, Any] = field(default_factory=dict)
    """Mapping rules: key, x, y, group_by, filter, …"""

    marks: List[Dict[str, Any]] = field(default_factory=list)
    """Ordered list of geom marks to draw."""

    scales: Dict[str, Any] = field(default_factory=dict)
    """Per-channel scale overrides (x, y, color, …)."""

    aesthetics: Dict[str, Any] = field(default_factory=dict)
    """Visual aesthetics: palette, alpha, linewidth, …"""

    layout: Dict[str, Any] = field(default_factory=dict)
    """Width, height, margins, legend position, …"""

    output: Dict[str, Any] = field(default_factory=dict)
    """format (svg|png|pdf), dpi, …"""

    @classmethod
    def from_yaml(cls, path: Path) -> "PlotSpec":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        p = raw.get("plot", raw)
        return cls(
            name=p.get("name", path.stem),
            plot_type=p["type"],
            title=p.get("title", ""),
            subtitle=p.get("subtitle", ""),
            description=p.get("description", ""),
            data=p.get("data", {}),
            marks=p.get("marks", []),
            scales=p.get("scales", {}),
            aesthetics=p.get("aesthetics", {}),
            layout=p.get("layout", {}),
            output=p.get("output", {}),
        )

    def override(self, params: Dict[str, Any]) -> "PlotSpec":
        """Return a shallow-merged copy with ``params`` overlaid on top-level keys."""
        spec = copy.deepcopy(self)
        for key, val in params.items():
            if isinstance(val, dict) and isinstance(getattr(spec, key, None), dict):
                getattr(spec, key).update(val)
            else:
                setattr(spec, key, val)
        return spec


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PlotRegistry:
    """Discovers and caches YAML specs from the ``plot_library/`` directory."""

    _cache: Dict[str, PlotSpec] = {}

    @classmethod
    def load(cls, name: str, lib_dir: Optional[Path] = None) -> PlotSpec:
        """Load a spec by name, using the built-in library by default."""
        cache_key = str(lib_dir or _PLOT_LIBRARY_DIR) + ":" + name
        if cache_key not in cls._cache:
            search_dirs = [lib_dir, _PLOT_LIBRARY_DIR] if lib_dir else [_PLOT_LIBRARY_DIR]
            for d in search_dirs:
                if d is None:
                    continue
                candidate = d / f"{name}.yaml"
                if candidate.exists():
                    cls._cache[cache_key] = PlotSpec.from_yaml(candidate)
                    break
            else:
                available = [p.stem for p in _PLOT_LIBRARY_DIR.glob("*.yaml")]
                raise ValueError(
                    f"Plot spec '{name}' not found in {_PLOT_LIBRARY_DIR}.  "
                    f"Available: {available}"
                )
        return cls._cache[cache_key]

    @classmethod
    def list(cls, lib_dir: Optional[Path] = None) -> List[str]:
        """Return names of all available specs."""
        d = lib_dir or _PLOT_LIBRARY_DIR
        return sorted(p.stem for p in d.glob("*.yaml"))

    @classmethod
    def describe(cls, name: str) -> str:
        """Return a human-readable description of a spec."""
        spec = cls.load(name)
        lines = [
            f"Plot: {spec.name}  (type: {spec.plot_type})",
            f"  {spec.title}",
        ]
        if spec.subtitle:
            lines.append(f"  {spec.subtitle}")
        if spec.description:
            lines.append(f"\n  {spec.description.strip()}")
        lines.append(f"\n  Data key: {spec.data.get('key', '?')}")
        lines.append(f"  Marks:    {[m['type'] for m in spec.marks]}")
        out_fmt = spec.output.get("format", "svg")
        size = f"{spec.layout.get('width', '?')}×{spec.layout.get('height', '?')}"
        lines.append(f"  Output:   {out_fmt}  {size}px")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Renderer dispatch
# ---------------------------------------------------------------------------

RendererFn = Callable[["PlotSpec", Any, Path], Path]
_RENDERERS: Dict[str, RendererFn] = {}


def register_renderer(plot_type: str) -> Callable[[RendererFn], RendererFn]:
    """Decorator to register a render function for a plot type."""
    def decorator(fn: RendererFn) -> RendererFn:
        _RENDERERS[plot_type] = fn
        return fn
    return decorator


def render_plot(
    spec: PlotSpec,
    data: Any,
    output_dir: Path,
    filename: Optional[str] = None,
) -> Path:
    """Render a plot to a file.

    Parameters
    ----------
    spec:
        Loaded and (optionally overridden) :class:`PlotSpec`.
    data:
        Raw data to plot.  Typically a list of dicts or a pandas DataFrame.
        May also be a ``StepOutput.data`` dict; the renderer extracts
        ``spec.data["key"]`` if needed.
    output_dir:
        Directory where the output file is written.
    filename:
        Override the output filename (default: ``<spec.name>.<format>``).

    Returns
    -------
    Path
        Absolute path of the written file.
    """
    renderer = _RENDERERS.get(spec.plot_type)
    if renderer is None:
        raise ValueError(
            f"No renderer registered for plot type '{spec.plot_type}'.  "
            f"Registered: {list(_RENDERERS)}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    if filename is None:
        fmt = spec.output.get("format", "svg")
        filename = f"{spec.name}.{fmt}"
    output_path = output_dir / filename
    result = renderer(spec, data, output_path)
    logger.info("Rendered %s → %s", spec.name, result)
    return result


# ---------------------------------------------------------------------------
# Utilities shared across renderers
# ---------------------------------------------------------------------------

def _resolve_data(spec: PlotSpec, data: Any) -> Any:
    """Extract the relevant records from ``data`` using spec.data.key."""
    key = spec.data.get("key")
    if key and isinstance(data, dict) and key in data:
        return data[key]
    return data


def _palette_for_spec(spec: PlotSpec) -> Dict[str, str]:
    return spec.aesthetics.get("palette", {})


def _fmt(spec: PlotSpec) -> str:
    return spec.output.get("format", "svg")


def _figsize(spec: PlotSpec):
    w = spec.layout.get("width", 800)
    h = spec.layout.get("height", 500)
    if isinstance(h, str):  # "auto"
        h = 500
    return w / 100, h / 100   # matplotlib inches at 100dpi


# ---------------------------------------------------------------------------
# Radar renderer
# ---------------------------------------------------------------------------

@register_renderer("radar")
def _render_radar(spec: PlotSpec, data: Any, output_path: Path) -> Path:
    """Render a radar / spider chart."""
    import math
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    records = _resolve_data(spec, data)
    if not records:
        raise ValueError(f"Plot '{spec.name}': no data found for key '{spec.data.get('key')}'")

    x_key     = spec.data.get("x", "dimension")
    y_key     = spec.data.get("y", "score")
    group_key = spec.data.get("group_by", "scenario")

    # Collect dimensions and groups
    dimensions = list(dict.fromkeys(r[x_key] for r in records))
    groups     = list(dict.fromkeys(r[group_key] for r in records if group_key in r))

    # Build value matrix: group → ordered scores per dimension
    values: Dict[str, List[float]] = {}
    for rec in records:
        g = rec.get(group_key, "default")
        values.setdefault(g, {})
        values[g][rec[x_key]] = float(rec.get(y_key, 0))

    N   = len(dimensions)
    angles = [2 * math.pi * i / N for i in range(N)] + [0]  # close polygon

    fig, ax = plt.subplots(
        figsize=_figsize(spec), subplot_kw=dict(polar=True)
    )

    palette = _palette_for_spec(spec)
    default_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    for idx, group in enumerate(groups):
        color = palette.get(group, default_colors[idx % len(default_colors)])
        vals  = [values.get(group, {}).get(d, 0) for d in dimensions] + \
                [values.get(group, {}).get(dimensions[0], 0)]
        ax.fill(angles, vals, alpha=0.25, color=color)
        ax.plot(angles, vals, color=color, linewidth=2, label=group)
        ax.scatter(angles[:-1], vals[:-1], color=color, s=36, zorder=5)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dimensions, size=9)
    y_scale = spec.scales.get("y", {})
    domain  = y_scale.get("domain", [0, 1])
    ax.set_ylim(domain[0], domain[1])
    ticks = y_scale.get("ticks", [0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticks(ticks)
    ax.set_yticklabels([str(t) for t in ticks], size=7, color="grey")

    if spec.title:
        fig.suptitle(spec.title, fontsize=12, fontweight="bold", y=1.02)
    if spec.subtitle:
        ax.set_title(spec.subtitle, fontsize=9, color="grey", pad=20)

    if spec.layout.get("legend", True):
        ax.legend(loc="lower right", fontsize=8,
                  bbox_to_anchor=(1.3, -0.1), framealpha=0.8)

    fig.tight_layout()
    fig.savefig(output_path, format=_fmt(spec), bbox_inches="tight",
                dpi=spec.output.get("dpi", 150))
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# Horizontal bar renderer
# ---------------------------------------------------------------------------

@register_renderer("bar_h")
def _render_bar_h(spec: PlotSpec, data: Any, output_path: Path) -> Path:
    """Render a horizontal bar chart, optionally with error bars."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    records = _resolve_data(spec, data)
    if not records:
        raise ValueError(f"Plot '{spec.name}': no data")

    x_key   = spec.data.get("x", "mean")
    y_key   = spec.data.get("y", "capability")
    err_key = spec.data.get("error")

    # Sort
    sort_by = spec.scales.get("y", {}).get("sort_by", x_key)
    records = sorted(records, key=lambda r: r.get(sort_by, 0), reverse=True)

    labels = [r[y_key] for r in records]
    values = [float(r.get(x_key, 0)) for r in records]
    errors = [float(r.get(err_key, 0)) for r in records] if err_key else None

    palette  = _palette_for_spec(spec)
    pos_col  = palette.get("positive", "#2ca02c")
    neg_col  = palette.get("negative", "#d62728")
    thr      = spec.aesthetics.get("positive_threshold", 0.0)
    bar_colors = [pos_col if v >= thr else neg_col for v in values]

    figw, figh = _figsize(spec)
    fig, ax    = plt.subplots(figsize=(figw, figh))

    y_pos = np.arange(len(labels))
    ax.barh(y_pos, values, color=bar_colors, height=0.6,
            xerr=errors, capsize=4, error_kw={"elinewidth": 1})

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, size=9)
    ax.axvline(0, color="#888888", linewidth=1, linestyle="--")

    x_label = spec.scales.get("x", {}).get("label", x_key)
    y_label = spec.scales.get("y", {}).get("label", y_key)
    ax.set_xlabel(x_label, size=9)
    ax.set_ylabel(y_label, size=9)

    # Value labels
    for annotation in spec.layout.get("annotations", []):
        if annotation.get("type") == "value_label":
            fmt_str = annotation.get("format", ".3f")
            for xi, yi in zip(values, y_pos):
                offset = 0.005 * (max(values) - min(values) or 1)
                ax.text(xi + (offset if xi >= 0 else -offset), yi,
                        f"{xi:{fmt_str}}", va="center",
                        ha="left" if xi >= 0 else "right", size=8)

    if spec.title:
        ax.set_title(spec.title, fontsize=11, fontweight="bold")
    if spec.subtitle:
        ax.text(0.5, 1.01, spec.subtitle, ha="center", va="bottom",
                transform=ax.transAxes, fontsize=8, color="grey")

    fig.tight_layout()
    fig.savefig(output_path, format=_fmt(spec), bbox_inches="tight",
                dpi=spec.output.get("dpi", 150))
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# Heatmap renderer
# ---------------------------------------------------------------------------

@register_renderer("heatmap")
def _render_heatmap(spec: PlotSpec, data: Any, output_path: Path) -> Path:
    """Render a 2-D heatmap."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    records = _resolve_data(spec, data)
    if not records:
        raise ValueError(f"Plot '{spec.name}': no data")

    x_key = spec.data.get("x", "dimension")
    y_key = spec.data.get("y", "challenge")
    v_key = spec.data.get("value", "delta")

    xs = list(dict.fromkeys(r[x_key] for r in records))
    ys = list(dict.fromkeys(r[y_key] for r in records))

    matrix = np.zeros((len(ys), len(xs)))
    for rec in records:
        xi = xs.index(rec[x_key])
        yi = ys.index(rec[y_key])
        matrix[yi, xi] = float(rec.get(v_key, 0))

    color_cfg = spec.scales.get("color", {})
    cmap   = color_cfg.get("palette", "RdYlGn")
    domain = color_cfg.get("domain", [-1, 1])
    center = color_cfg.get("center", 0)
    vmin, vmax = domain

    figw, figh = _figsize(spec)
    fig, ax    = plt.subplots(figsize=(figw, figh))

    im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=35, ha="right", size=9)
    ax.set_yticks(range(len(ys)))
    ax.set_yticklabels(ys, size=9)

    mark_cfg = spec.marks[0] if spec.marks else {}
    if mark_cfg.get("annotate", True):
        ann_fmt = mark_cfg.get("annotation_format", "+.2f")
        ann_fs  = int(mark_cfg.get("annotation_fontsize", 9))
        for yi in range(len(ys)):
            for xi in range(len(xs)):
                v = matrix[yi, xi]
                ax.text(xi, yi, f"{v:{ann_fmt}}", ha="center", va="center",
                        fontsize=ann_fs, color="black")

    x_label = spec.scales.get("x", {}).get("label", x_key)
    y_label = spec.scales.get("y", {}).get("label", y_key)
    ax.set_xlabel(x_label, size=9)
    ax.set_ylabel(y_label, size=9)

    if spec.layout.get("colorbar", True):
        cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
        cb.set_label(spec.layout.get("colorbar_label", v_key), size=8)

    if spec.title:
        ax.set_title(spec.title, fontsize=11, fontweight="bold")
    if spec.subtitle:
        ax.text(0.5, 1.01, spec.subtitle, ha="center", va="bottom",
                transform=ax.transAxes, fontsize=8, color="grey")

    fig.tight_layout()
    fig.savefig(output_path, format=_fmt(spec), bbox_inches="tight",
                dpi=spec.output.get("dpi", 150))
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# Gantt renderer
# ---------------------------------------------------------------------------

@register_renderer("gantt")
def _render_gantt(spec: PlotSpec, data: Any, output_path: Path) -> Path:
    """Render a Gantt-style execution timeline."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from datetime import datetime

    records = _resolve_data(spec, data)
    if not records:
        raise ValueError(f"Plot '{spec.name}': no data")

    # Apply filter (simple 'not in' filter from spec)
    filt = spec.data.get("filter", "")
    if "not in" in filt:
        # parse: "<field> not in ['A', 'B']"
        # simple eval-safe version
        try:
            parts = filt.split("not in")
            fld   = parts[0].strip()
            excl  = yaml.safe_load(parts[1].strip())
            records = [r for r in records if r.get(fld) not in excl]
        except Exception as exc:
            logger.debug("plot filter ignored (%r): %s", filt, exc)

    y_key      = spec.data.get("y", "agent_id")
    start_key  = spec.data.get("x_start", "start_ts")
    end_key    = spec.data.get("x_end",   "end_ts")
    group_key  = spec.data.get("group_by", "node_type")

    # Parse timestamps → float ms
    def _to_ms(v) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return datetime.fromisoformat(str(v)).timestamp() * 1000
        except Exception:
            return None

    spans = []
    for rec in records:
        t0 = _to_ms(rec.get(start_key))
        t1 = _to_ms(rec.get(end_key))
        if t0 is None:
            continue
        if t1 is None:
            t1 = t0 + 50   # minimum bar width for point events
        spans.append({
            "agent":  rec.get(y_key, "?"),
            "type":   rec.get(group_key, "?"),
            "t0":     t0,
            "t1":     t1,
            "label":  rec.get("call_id", ""),
        })

    if not spans:
        raise ValueError("trajectory_gantt: no span records in upstream data")

    # Normalize time → relative ms
    t_min = min(s["t0"] for s in spans)
    for s in spans:
        s["t0"] -= t_min
        s["t1"] -= t_min

    agents = sorted(set(s["agent"] for s in spans),
                    key=lambda a: min(s["t0"] for s in spans if s["agent"] == a))

    color_cfg = spec.scales.get("color", {}).get("palette", {})
    default_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    all_types  = sorted(set(s["type"] for s in spans))
    type_color: Dict[str, str] = {}
    for i, t in enumerate(all_types):
        type_color[t] = color_cfg.get(t, default_colors[i % len(default_colors)])

    row_h    = spec.layout.get("row_height", 32) / 100
    n_agents = len(agents)
    figw     = spec.layout.get("width", 1100) / 100
    figh     = max(3.0, n_agents * row_h + 2.0)
    fig, ax  = plt.subplots(figsize=(figw, figh))

    for row_idx, agent in enumerate(agents):
        agent_spans = [s for s in spans if s["agent"] == agent]
        for s in agent_spans:
            color   = type_color.get(s["type"], "#aaaaaa")
            dur_ms  = s["t1"] - s["t0"]
            bar     = mpatches.FancyBboxPatch(
                (s["t0"], row_idx - 0.35), dur_ms, 0.7,
                boxstyle="round,pad=0.01",
                linewidth=0.4, edgecolor="#ffffff",
                facecolor=color, alpha=0.85,
            )
            ax.add_patch(bar)
            min_w = spec.marks[0].get("min_width_ms", 200) if spec.marks else 200
            if dur_ms >= min_w:
                lbl = s["label"][:8] if s["label"] else ""
                ax.text(s["t0"] + dur_ms / 2, row_idx, lbl,
                        ha="center", va="center", fontsize=6, color="white",
                        clip_on=True)

    ax.set_yticks(range(n_agents))
    ax.set_yticklabels(agents, size=8)
    ax.set_xlim(0, max(s["t1"] for s in spans) * 1.02)
    ax.set_ylim(-0.7, n_agents - 0.3)
    ax.set_xlabel("Elapsed (ms)", size=9)

    legend_patches = [
        mpatches.Patch(color=type_color[t], label=t) for t in all_types
    ]
    if spec.layout.get("legend", True):
        ax.legend(handles=legend_patches, fontsize=7,
                  loc="upper right", framealpha=0.9)

    if spec.title:
        ax.set_title(spec.title, fontsize=11, fontweight="bold")
    if spec.subtitle:
        ax.text(0.5, 1.01, spec.subtitle, ha="center", va="bottom",
                transform=ax.transAxes, fontsize=8, color="grey")

    fig.tight_layout()
    fig.savefig(output_path, format=_fmt(spec), bbox_inches="tight",
                dpi=spec.output.get("dpi", 150))
    plt.close(fig)
    return output_path
