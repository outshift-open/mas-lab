#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.library.lab.plots — standard plot library for MAS Lab.

Functions
---------
execution_chain_graph(source, *, level='agents', ...)
    Build a matplotlib Figure showing the execution chain at the requested
    granularity level.

    ``level='agents'``
        One node per agent visit (sequence view), preserving repetitions and
        directed transitions in execution order.

    ``level='calls'``
        One node per call event (agent boundary marker / LLM call / tool call),
        laid out in a linear grid.

Usage::

    from mas.library.lab.plots import execution_chain_graph

    # Trajectory companion from extract_trajectories
    df = exp.artifacts(kind='dataframe')[0]
    fig = execution_chain_graph(df, level='agents', palette=p)

    # Or pass the DataFrameArtifact directly
    fig = execution_chain_graph(exp_art, level='agents', palette=p)
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execution_chain_graph(
    source: Any,
    *,
    level: str = "agents",
    run_id: Optional[str] = None,
    palette: Optional[Any] = None,
    figsize: Optional[Tuple[float, float]] = None,
) -> Any:
    """Return a matplotlib Figure visualising the MAS execution chain.

    Parameters
    ----------
    source:
        One of:

        * :class:`~mas.lab.artifacts.KnowledgeGraph` — ``data`` must be a
          trajectory dict with a ``"calls"`` key.
        * :class:`~mas.lab.artifacts.DataFrameArtifact` — calls
          :meth:`~mas.lab.artifacts.DataFrameArtifact.load_companion` internally.
        * :class:`pandas.DataFrame` — a call-level frame (from
          ``exp_art.load_companion()``).
        * ``dict`` — a raw trajectory dict with a ``"calls"`` key.

    level:
        Granularity of the graph:

        ``'agents'`` *(default)*
            One node per agent visit in chronological order. Directed edges link
            each visit to the next, preserving repetitions and return hops.

        ``'calls'``
            One node per call event (agent boundary markers, LLM calls, tool
            calls), laid out in a linear grid of circles.

    run_id:
        When *source* is a multi-run DataFrame, select this run.  Defaults to
        the run closest to the median call count.

    palette:
        A :class:`~mas.lab.palette.Palette` instance.  If *None*, a fresh
        default palette is created.

    figsize:
        Matplotlib figure size ``(width, height)`` in inches.  Sensible
        defaults are chosen per level.

    Returns
    -------
    matplotlib.figure.Figure
        The finished figure (also shown inline in Jupyter via plt.show()).
    """
    from mas.lab.palette import Palette

    p = palette if palette is not None else Palette()
    calls = _extract_calls(source, run_id=run_id)
    resolved_run_id = _resolve_run_id(source, run_id, calls)

    if level == "agents":
        return _agent_graph(calls, p=p, run_id=resolved_run_id, figsize=figsize)
    elif level == "calls":
        return _call_graph(calls, p=p, run_id=resolved_run_id, figsize=figsize)
    else:
        raise ValueError(f"Unknown level {level!r}; expected 'agents' or 'calls'")


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------

def _extract_calls(
    source: Any,
    *,
    run_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Extract a flat list of call dicts from *source*."""

    # KnowledgeGraph artifact
    try:
        from mas.lab.artifacts import KnowledgeGraph
        if isinstance(source, KnowledgeGraph):
            data = source.data if source.data is not None else source.load_json()
            return list(data.get("calls", []))
    except ImportError:
        pass

    # DataFrameArtifact
    try:
        from mas.lab.artifacts import DataFrameArtifact
        if isinstance(source, DataFrameArtifact):
            df = source.load_companion()
            return _calls_from_df(df, run_id=run_id)
    except ImportError:
        pass

    # pandas DataFrame
    try:
        import pandas as pd
        if isinstance(source, pd.DataFrame):
            return _calls_from_df(source, run_id=run_id)
    except ImportError:
        pass

    # raw trajectory dict
    if isinstance(source, dict):
        return list(source.get("calls", []))

    raise TypeError(
        f"Unsupported source type {type(source).__name__}. "
        "Pass a KnowledgeGraph, DataFrameArtifact, DataFrame, or dict."
    )


def _calls_from_df(df: Any, *, run_id: Optional[str]) -> List[Dict[str, Any]]:
    """Select one run from a call-level DataFrame and return a list of call dicts."""
    if run_id is None:
        counts = df.groupby("run_id")["call_idx"].count().reset_index(name="n")
        med = int(counts["n"].median())
        run_id = counts.iloc[(counts["n"] - med).abs().argsort().iloc[0]]["run_id"]

    sub = df[df["run_id"] == run_id].sort_values("call_idx").reset_index(drop=True)
    calls = []
    for _, row in sub.iterrows():
        raw = row.get("tool_calls", "[]")
        if isinstance(raw, str):
            try:
                tool_calls = json.loads(raw)
            except Exception:
                tool_calls = []
        elif isinstance(raw, list):
            tool_calls = raw
        else:
            tool_calls = []
        calls.append({
            "agent_id": str(row.get("agent", row.get("agent_id", "?"))),
            "call_idx": int(row.get("call_idx", 0)),
            "tool_calls": tool_calls,
        })
    return calls


def _resolve_run_id(
    source: Any,
    run_id: Optional[str],
    calls: List[Dict],
) -> str:
    """Return the best human-readable run_id for plot titles."""
    if run_id:
        return run_id
    try:
        from mas.lab.artifacts import KnowledgeGraph
        if isinstance(source, KnowledgeGraph):
            return source.run_id or (source.data or {}).get("run_id", "")
    except ImportError:
        pass
    if isinstance(source, dict):
        return source.get("run_id", "")
    return ""


# ---------------------------------------------------------------------------
# Agent-level directed sequence graph
# ---------------------------------------------------------------------------

def _agent_graph(
    calls: List[Dict[str, Any]],
    *,
    p: Any,
    run_id: str,
    figsize: Optional[Tuple[float, float]],
) -> Any:
    """Directed sequence graph: one node per agent visit, with repetitions."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    visit_seq: List[str] = []
    agent_stats: Dict[str, Dict[str, int]] = {}
    for c in calls:
        a = c.get("agent_id", c.get("agent", "?"))
        visit_seq.append(a)
        if a not in agent_stats:
            agent_stats[a] = {"n_calls": 0, "n_tools": 0}
        agent_stats[a]["n_calls"] += 1
        agent_stats[a]["n_tools"] += len(c.get("tool_calls") or [])

    if not visit_seq:
        visit_seq = ["?"]

    collapsed_visits: List[Dict[str, Any]] = []
    for a in visit_seq:
        if not collapsed_visits or collapsed_visits[-1]["agent"] != a:
            collapsed_visits.append({"agent": a, "n_calls": 1})
        else:
            collapsed_visits[-1]["n_calls"] += 1

    n = len(collapsed_visits)
    STEP_X = 1.9
    pos = [i * STEP_X for i in range(n)]

    width = max(6.5, n * STEP_X + 1.0)
    fig, ax = plt.subplots(figsize=figsize or (min(width, 24.0), 4.2))
    ax.set_facecolor(p.bg)
    fig.patch.set_facecolor(p.bg)
    ax.set_xlim(-0.8, (n - 1) * STEP_X + 0.8)
    ax.set_ylim(-1.9, 1.9)
    ax.axis("off")

    for i in range(n - 1):
        x0, x1 = pos[i], pos[i + 1]
        is_return = i > 0 and collapsed_visits[i + 1]["agent"] == collapsed_visits[i - 1]["agent"]
        rad = -0.25 if is_return else 0.0
        ax.annotate(
            "",
            xy=(x1, 0),
            xytext=(x0, 0),
            arrowprops=dict(
                arrowstyle="-|>",
                color=p.lifeline,
                lw=1.5,
                alpha=0.85,
                connectionstyle=f"arc3,rad={rad:.2f}",
                mutation_scale=12,
            ),
        )

    NODE_R = 0.44
    agent_color = p.type_colors.get("AgentCall", p.agent)

    for i, visit in enumerate(collapsed_visits):
        a = visit["agent"]
        x = pos[i]
        ax.add_patch(mpatches.Circle(
            (x, 0), NODE_R,
            facecolor=agent_color, edgecolor="white", linewidth=1.8, zorder=4,
        ))
        short = a.replace("_agent", "").replace("_", "\n")
        ax.text(x, 0, short, ha="center", va="center",
                fontsize=6.5, color="white", fontweight="bold", zorder=5,
                multialignment="center")
        ax.text(
            x, -NODE_R - 0.18,
            f"step {i + 1}  ·  {visit['n_calls']} call(s)",
            ha="center", va="top", fontsize=6.5, color=p.label, zorder=5,
        )

    n_trans = max(0, n - 1)
    unique_agents = len(set(v["agent"] for v in collapsed_visits))
    label = f"{run_id}  ·  " if run_id else ""
    ax.set_title(
        f"Execution chain (agents, directed sequence)  —  {label}"
        f"{unique_agents} agents  ·  {n} visits  ·  {n_trans} transitions",
        fontsize=9, color=p.title, pad=6, fontweight="bold",
    )
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Call-level linear grid
# ---------------------------------------------------------------------------

def _call_graph(
    calls: List[Dict[str, Any]],
    *,
    p: Any,
    run_id: str,
    figsize: Optional[Tuple[float, float]],
) -> Any:
    """Linear grid of call nodes: agent boundaries, LLM calls, tool calls."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Circle
    import numpy as np

    nodes: List[Dict] = []
    prev_agent = None
    for c in calls:
        agent_name = c.get("agent_id", c.get("agent", "?"))
        if agent_name != prev_agent:
            nodes.append({
                "t": "AgentCall",
                "short": str(agent_name).split("_")[0][:6],
                "full": str(agent_name),
            })
            prev_agent = agent_name
        nodes.append({"t": "LLMCall", "short": "LLM", "full": f"LLM #{int(c.get('call_idx', 0))}"})
        tool_calls = c.get("tool_calls") or []
        if isinstance(tool_calls, str):
            try:
                tool_calls = json.loads(tool_calls)
            except Exception:
                tool_calls = []
        for tc in tool_calls:
            name = tc if isinstance(tc, str) else tc.get("name", "tool")
            nodes.append({"t": "ToolCall", "short": "⚡", "full": name})

    COLS = 16
    NODE_R = 0.38
    STEP_X = 1.25
    STEP_Y = 2.6
    n_nodes = len(nodes)
    n_rows = math.ceil(n_nodes / COLS)

    fig, ax = plt.subplots(figsize=figsize or (min(COLS * STEP_X + 1.0, 22), n_rows * STEP_Y + 1.6))
    ax.set_facecolor(p.bg)
    fig.patch.set_facecolor(p.bg)
    ax.set_xlim(-0.8, COLS * STEP_X + 0.2)
    ax.set_ylim(-(n_rows * STEP_Y) - 0.5, 1.5)
    ax.axis("off")

    coords = [
        (col_i * STEP_X, -(i // COLS) * STEP_Y)
        for i, col_i in enumerate(i % COLS for i in range(n_nodes))
    ]

    for i in range(n_nodes - 1):
        x0, y0 = coords[i]
        x1, y1 = coords[i + 1]
        row0, row1 = i // COLS, (i + 1) // COLS
        if row0 == row1:
            dx = np.sign(x1 - x0)
            ax.annotate(
                "",
                xy=(x1 - dx * NODE_R, y1),
                xytext=(x0 + dx * NODE_R, y0),
                arrowprops=dict(arrowstyle="->", color=p.lifeline, lw=1.1, mutation_scale=10),
            )
        else:
            ax.annotate(
                "",
                xy=(x1 + NODE_R, y1),
                xytext=(x0, y0 - NODE_R),
                arrowprops=dict(
                    arrowstyle="->",
                    color=p.lifeline,
                    lw=1.1,
                    mutation_scale=10,
                    connectionstyle="arc3,rad=-0.35",
                ),
            )

    for i, node in enumerate(nodes):
        x, y = coords[i]
        color = p.type_colors.get(node["t"], p.default)
        ax.add_patch(Circle((x, y), NODE_R, facecolor=color, edgecolor="white", linewidth=1.4, zorder=3))
        ax.text(x, y, node["short"], ha="center", va="center", fontsize=7, color="white", fontweight="bold", zorder=4)
        if node["t"] == "AgentCall":
            ax.text(
                x, y - NODE_R - 0.15, node["full"],
                ha="center", va="top", fontsize=5.5, color=p.label, zorder=4, rotation=30,
            )

    ax.legend(
        handles=[
            mpatches.Patch(facecolor=p.type_colors.get("AgentCall", "#0e7490"), edgecolor="white", label="Agent boundary"),
            mpatches.Patch(facecolor=p.type_colors.get("LLMCall", "#ea580c"), edgecolor="white", label="LLM call"),
            mpatches.Patch(facecolor=p.type_colors.get("ToolCall", "#16a34a"), edgecolor="white", label="Tool call  ⚡"),
            mpatches.Patch(facecolor=p.type_colors.get("MemoryCall", "#2563eb"), edgecolor="white", label="Memory call"),
        ],
        loc="upper right", fontsize=8,
        facecolor=p.bg, edgecolor=p.grid, labelcolor=p.label,
    )
    title = (
        f"Execution chain (calls) — {run_id}  ({n_nodes} nodes)"
        if run_id else f"Execution chain (calls) — {n_nodes} nodes"
    )
    ax.set_title(title, fontsize=10, color=p.title, pad=8, fontweight="bold")
    plt.tight_layout()
    return fig
