#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Public trajectory plot API."""

from pathlib import Path
from typing import Union

from mas.lab.plots.trajectory.loading import load_trace
from mas.lab.plots.trajectory.extract import (
    _extract_agent_order,
    _extract_delegations,
    _extract_user_frame,
)
from mas.lab.plots.trajectory.highlights import (
    _resolve_highlights,
    _resolve_keyword_highlights,
)
from mas.lab.plots.trajectory.mermaid import _fmt_mermaid, _fmt_table
from mas.lab.plots.trajectory.html import _fmt_html
from mas.lab.plots.trajectory.svg import _fmt_svg_mermaid, _fmt_svg_native

def plot_trajectory(
    trace: Union[str, Path, list[dict]],
    fmt: str = "mermaid",
    include_prompts: bool = True,
    highlights: list[str] | None = None,
    highlight_agents: list[str] | None = None,
    highlight_keywords: list[str] | None = None,
    title: str | None = None,
) -> str:
    """Generate a trajectory diagram from a MAS event trace.

    Parameters
    ----------
    trace:
        A list of event dicts (already loaded), a path to a JSONL file, or a
        run_id string.  Strings / Paths are forwarded to :func:`load_trace`.
    fmt:
        Output format.  One of ``"mermaid"`` (default), ``"table"``, ``"html"``,
        ``"svg"``.
    include_prompts:
        When ``True`` (default), delegation task text is shown on diagram edges.
        Set to ``False`` for compact output.
    highlights:
        List of delegation identifiers to visually flag.  Each entry is either:
        - A correlation-id prefix (e.g. ``"f19445b6"``) — prefix-matched.
        - A 1-based index string (e.g. ``"2"``) — matches delegation #2.
        Highlighted arrows are rendered in amber with a ⚠️ marker.
    highlight_agents:
        List of agent names whose participant/actor nodes to highlight in amber.
        E.g. ``["telemetry", "backend", "db"]`` marks the agents with blind spots.
    highlight_keywords:
        List of keywords (case-insensitive substrings) to auto-detect in
        delegation task/output text.  Matching delegations are highlighted
        exactly like entries in *highlights*.

    Returns
    -------
    str
        Formatted diagram string ready to print or write to a file.
    """
    if not isinstance(trace, list):
        trace = load_trace(trace)

    if not trace:
        return "(empty trace — no events)"

    delegations = _extract_delegations(trace)
    agents = _extract_agent_order(trace)

    # Mark highlighted delegations before inserting the user frame so that
    # user-provided indices refer to real agent-to-agent delegations (1-based).
    hl_idxs = (
        _resolve_highlights(delegations, highlights)
        | _resolve_keyword_highlights(delegations, highlight_keywords)
    )
    for i in hl_idxs:
        delegations[i] = {**delegations[i], "highlighted": True}

    # Split the user frame into fwd-only (first) and ret-only (last) so that
    # all internal agent delegations appear sandwiched between prompt and answer.
    user_frame = _extract_user_frame(trace)
    if user_frame and user_frame["target"] in agents:
        fwd = {**user_frame, "fwd_only": True}
        ret = {
            **user_frame,
            "source": user_frame["target"],   # entry-agent → User
            "target": "User",
            "ret_only": True,
        }
        delegations = [fwd] + delegations + [ret]
        agents = ["User"] + [a for a in agents if a != "User"]

    fmt = fmt.lower()
    if fmt == "mermaid":
        return _fmt_mermaid(delegations, agents, include_prompts)
    elif fmt == "md":
        diagram = _fmt_mermaid(delegations, agents, include_prompts)
        fenced = f"```mermaid\n{diagram}\n```"
        if title:
            return f"## {title}\n\n{fenced}"
        return fenced
    elif fmt == "table":
        return _fmt_table(delegations, include_prompts)
    elif fmt == "html":
        return _fmt_html(delegations, agents, include_prompts, highlight_agents=highlight_agents)
    elif fmt == "svg":
        return _fmt_svg_mermaid(delegations, agents, include_prompts)
    elif fmt == "svg_native":
        return _fmt_svg_native(delegations, agents, include_prompts, highlight_agents=highlight_agents)
    else:
        raise ValueError(f"Unknown format '{fmt}'. Choose: mermaid, md, table, html, svg, svg_native")
