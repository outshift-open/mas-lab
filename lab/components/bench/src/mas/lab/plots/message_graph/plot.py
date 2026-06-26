#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Main message-graph render function."""

import html as _html
from typing import Any

from mas.lab.plots.kg_adapter import KGView
from mas.lab.plots.message_graph.constants import *
from mas.lab.plots.message_graph.helpers import _agent_color, _dur_str, _preview, _tip_attrs
from mas.lab.plots.message_graph.theme import _HTML_WRAPPER, _build_svg_css
from mas.lab.plots.message_graph.extract import _extract, _find_root_agent_id, _assign_iterations
from mas.lab.plots.message_graph.layout import (
    _lane_y, _slot_cx, _box_left, _box_right, _box_top, _fmt_time_s, _nice_time_interval,
)

# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def plot_message_graph(
    kg: dict,
    title: str = "Message Graph",
    fmt: str = "svg",
    theme: str = "auto",
    hover: bool = True,
    time_axis: bool = True,
    respect_timing: bool = True,
) -> str:
    """Render a message-flow diagram and return SVG or HTML string.

    Args:
        kg:              Knowledge-graph dict.
        title:           Diagram title.
        fmt:             ``"svg"`` (default) or ``"html"``.
        theme:           ``"auto"`` (default), ``"light"``, or ``"dark"``.
        hover:           When ``True`` (default) attach tooltip data to boxes
                         and tool squares, and include the floating tooltip
                         panel in HTML output.
        time_axis:       When ``True`` (default) draw a horizontal time axis
                         below the diagram lanes showing elapsed seconds.
        respect_timing:  When ``True`` (default) set box widths and x-positions
                         proportional to actual LLM call durations.  Falls back
                         to equal-slot layout when timing data is unavailable.
    """
    standalone = (fmt != "html")  # True → pure SVG file; False → embedded in HTML
    view = KGView.from_kg(kg)
    llm_calls, tool_by_llm = _extract(view)

    if not llm_calls:
        return (
            '<svg viewBox="0 0 320 60" xmlns="http://www.w3.org/2000/svg">'
            '<text x="160" y="35" text-anchor="middle" font-family="sans-serif"'
            ' font-size="13" fill="#666">No LLM calls found in this run.</text>'
            "</svg>"
        )

    root_agent_id = _find_root_agent_id(view)
    iterations = _assign_iterations(llm_calls, root_agent_id)

    # Build ordered agent list (first appearance order)
    agent_order: list[str] = []
    seen_agents: set[str] = set()
    for c in llm_calls:
        aid = c["agent_id"] or "?"
        if aid not in seen_agents:
            seen_agents.add(aid)
            agent_order.append(aid)

    agent_idx_map: dict[str, int] = {a: i for i, a in enumerate(agent_order)}
    n_lanes = len(agent_order)
    n_calls = len(llm_calls)

    # ── Per-call geometry ──────────────────────────────────────────────────
    # respect_timing=True : box x and width are proportional to actual duration.
    # Fallback to equal-width slots when timing data is absent.
    _use_timing = (
        respect_timing
        and all(c.get("start_ts") is not None for c in llm_calls)
    )
    if _use_timing:
        t_min_ts = min(c["start_ts"] for c in llm_calls)
        t_max_ts = max((c.get("end_ts") or c["start_ts"]) for c in llm_calls)
        t_span   = max(t_max_ts - t_min_ts, 0.5)
        # px/s: target ~30 px per average call slot, 4 px/s min, 80 px/s max
        _pps = min(max(max(n_calls * 30, 600) / t_span, 4.0), 80.0)
        call_bx: list[float] = []
        call_bw: list[float] = []
        for c in llm_calls:
            bx  = _MARGIN_LEFT + (c["start_ts"] - t_min_ts) * _pps
            dur = max((c.get("end_ts") or c["start_ts"]) - c["start_ts"], 0.0)
            bw  = max(_BOX_W_MIN, dur * _pps)
            call_bx.append(bx)
            call_bw.append(bw)
        call_cx: list[float] = [call_bx[i] + call_bw[i] / 2 for i in range(n_calls)]
        call_rx: list[float] = [call_bx[i] + call_bw[i]     for i in range(n_calls)]
        canvas_w = int(max(call_rx)) + _MARGIN_RIGHT + 4
    else:
        t_min_ts = 0.0
        t_span   = 1.0
        _pps     = 1.0
        call_bx  = [_box_left(i)  for i in range(n_calls)]
        call_bw  = [float(_BOX_W) for _ in range(n_calls)]
        call_cx  = [_slot_cx(i)   for i in range(n_calls)]
        call_rx  = [_box_right(i) for i in range(n_calls)]
        canvas_w = _MARGIN_LEFT + n_calls * _SLOT_W + _MARGIN_RIGHT

    _axis_extra = _TIME_AXIS_H if time_axis else 0
    canvas_h  = _MARGIN_TOP + n_lanes * _LANE_STEP + _MARGIN_BOTTOM + _axis_extra + _LEGEND_H
    diagram_h = canvas_h - _LEGEND_H  # boundary between diagram and legend area

    parts: list[str] = []

    # ── background rect (picks up --mg-bg via CSS) ──────────────────────────
    parts.append('<rect class="mg-bg" width="100%" height="100%"/>')

    # ── defs (arrow marker) ────────────────────────────────────────────────
    parts.append(
        '<defs>'
        '<marker id="mg-arrow" viewBox="0 -5 10 10" refX="10" refY="0"'
        ' markerUnits="userSpaceOnUse" markerWidth="6" markerHeight="6"'
        ' orient="auto">'
        '<path class="mg-arrow-path" d="M0,-5 L10,0 L0,5 Z"/>'
        '</marker>'
        '</defs>'
    )

    # ── iteration bands ────────────────────────────────────────────────────
    iter_groups: dict[int, list[int]] = {}
    for slot_i, it in enumerate(iterations):
        iter_groups.setdefault(it, []).append(slot_i)

    band_y = _MARGIN_TOP
    band_h = n_lanes * _LANE_STEP
    band_parts: list[str] = []
    for it in sorted(iter_groups):
        indices = iter_groups[it]
        x_min = min(call_bx[s] for s in indices)
        x_max = max(call_rx[s] for s in indices)
        w = x_max - x_min
        alt_cls = " iteration-band--alt" if it % 2 == 1 else ""
        band_parts.append(
            f'<rect class="iteration-band{alt_cls}"'
            f' x="{x_min:.2f}" y="{band_y}" width="{w:.2f}" height="{band_h}"/>'
        )
        lx = (x_min + x_max) / 2
        band_parts.append(
            f'<text class="iteration-label" x="{lx:.2f}" y="{_MARGIN_TOP - 6}">'
            f'Iter {it}</text>'
        )
    parts.append('<g class="band-layer">' + "".join(band_parts) + "</g>")

    # ── lane lines and labels ──────────────────────────────────────────────
    line_x1 = _MARGIN_LEFT - 10
    line_x2 = float(canvas_w - _MARGIN_RIGHT)
    lane_parts: list[str] = []
    for agent in agent_order:
        y = _lane_y(agent_idx_map, agent)
        label = _html.escape(agent)
        lane_parts.append(
            f'<line class="lane-line"'
            f' x1="{line_x1}" y1="{y}" x2="{line_x2:.1f}" y2="{y}"/>'
        )
        lane_parts.append(
            f'<text class="lane-label" x="{_MARGIN_LEFT - 14}" y="{y}">'
            f'{label}</text>'
        )
    parts.append('<g class="lane-layer">' + "".join(lane_parts) + "</g>")

    # ── chronological flow edges ───────────────────────────────────────────
    edge_parts: list[str] = []

    for i in range(n_calls - 1):
        c_i = llm_calls[i]
        c_j = llm_calls[i + 1]

        aid_i = c_i["agent_id"] or ""
        aid_j = c_j["agent_id"] or ""

        cy_i = _lane_y(agent_idx_map, aid_i)
        cy_j = _lane_y(agent_idx_map, aid_j)

        right_i = call_rx[i]
        left_j  = call_bx[i + 1]
        cx_j    = call_cx[i + 1]
        top_j   = cy_j - _BOX_H / 2

        if cy_i == cy_j:
            # Same lane — simple horizontal segment (no arrowhead)
            edge_parts.append(
                f'<path class="graph-edge"'
                f' d="M {right_i:.3f} {cy_i} L {left_j:.3f} {cy_i}"/>'
            )

        elif cy_j > cy_i:
            # Going DOWN (target lane lower on screen, y increases)
            # Step 1: horizontal from right_i to cx_j on source lane
            edge_parts.append(
                f'<path class="graph-edge"'
                f' d="M {right_i:.3f} {cy_i} L {cx_j:.3f} {cy_i}"/>'
            )
            # Step 2: vertical drop with arrowhead — stops at top of target box
            edge_parts.append(
                f'<path class="graph-edge" marker-end="url(#mg-arrow)"'
                f' d="M {cx_j:.3f} {cy_i} L {cx_j:.3f} {top_j - 1:.3f}"/>'
            )

        else:
            # Going UP (target lane higher on screen, y decreases)
            # Step 1: 2 px jog right, then vertical up with arrowhead to target lane
            bend_x = right_i + 2.0
            edge_parts.append(
                f'<path class="graph-edge" marker-end="url(#mg-arrow)"'
                f' d="M {right_i:.3f} {cy_i}'
                f' L {bend_x:.3f} {cy_i}'
                f' L {bend_x:.3f} {cy_j:.3f}"/>'
            )
            # Step 2: horizontal entry from bend_x to left edge of target box
            edge_parts.append(
                f'<path class="graph-edge"'
                f' d="M {bend_x:.3f} {cy_j} L {left_j:.3f} {cy_j}"/>'
            )

    parts.append('<g class="edge-layer">' + "".join(edge_parts) + "</g>")

    # ── tool-call squares ──────────────────────────────────────────────────
    tool_parts: list[str] = []
    for i, c in enumerate(llm_calls):
        cid = c["call_id"]
        tools = tool_by_llm.get(cid, [])
        if not tools:
            continue

        n_tools = len(tools)
        cx = call_cx[i]
        cy = _lane_y(agent_idx_map, c["agent_id"] or "")
        tick_y1 = cy + _BOX_H / 2
        tick_y2 = tick_y1 + _TOOL_TICK_H

        tool_parts.append(
            f'<line class="tool-tick"'
            f' x1="{cx:.3f}" y1="{tick_y1}" x2="{cx:.3f}" y2="{tick_y2}"/>'
        )

        total_w = n_tools * _TOOL_SIZE + (n_tools - 1) * _TOOL_GAP
        start_x = cx - total_w / 2
        for j, t in enumerate(tools):
            tx = start_x + j * (_TOOL_SIZE + _TOOL_GAP)
            _tname = t.get("tool_name") or t.get("label") or f"tool-{j + 1}"
            _tdur  = _dur_str(t["start_ts"], t.get("end_ts"))
            _tbody = (
                f"Agent: {t.get('agent_id', '')}\n"
                f"Duration: {_tdur}\n"
                f"\nInput:\n{_preview(t.get('input'), 220)}\n"
                f"\nOutput:\n{_preview(t.get('output'), 220)}"
            )
            _ta    = _tip_attrs(_tname, _tbody) if hover else ""
            _ttitle = (
                f'<title>{_html.escape(_tname)} \u00b7 {_tdur}</title>'
                if standalone and hover else ''
            )
            tool_parts.append(
                f'<g{_ta}>{_ttitle}'
                f'<rect class="tool-square"'
                f' x="{tx:.3f}" y="{tick_y2}"'
                f' width="{_TOOL_SIZE}" height="{_TOOL_SIZE}"/>'
                f'</g>'
            )

    parts.append('<g class="tool-layer">' + "".join(tool_parts) + "</g>")

    # ── LLM-call boxes (turn nodes) ────────────────────────────────────────
    node_parts: list[str] = []
    for i, c in enumerate(llm_calls):
        aid = c["agent_id"] or ""
        a_idx = agent_idx_map.get(aid, 0)
        color = _agent_color(a_idx)

        bx = call_bx[i]
        bw = call_bw[i]
        cy = _lane_y(agent_idx_map, aid)
        by = cy - _BOX_H / 2
        cx = call_cx[i]
        label = str(i + 1)

        _dur    = _dur_str(c["start_ts"], c.get("end_ts"))
        _model  = c.get("model") or "\u2014"
        _tlabel = f"{aid} \u2014 Turn {i + 1}"
        _tbody  = (
            f"Model:    {_model}\n"
            f"Duration: {_dur}\n"
            f"Call:     {(c.get('call_id') or '')[:36]}\n"
            f"\nInput:\n{_preview(c.get('input'), 350)}\n"
            f"\nOutput:\n{_preview(c.get('output'), 350)}"
        )
        _ta     = _tip_attrs(_tlabel, _tbody) if hover else ""
        _ttitle = (
            f'<title>{_html.escape(_tlabel)} \u00b7 {_dur}</title>'
            if standalone and hover else ''
        )
        node_parts.append(
            f'<g class="turn-node"{_ta}'
            f' data-agent="{_html.escape(aid)}" data-color="{color}">'
            f'{_ttitle}'
            f'<rect class="turn-rect"'
            f' x="{bx:.3f}" y="{by:.3f}"'
            f' width="{bw:.2f}" height="{_BOX_H}"'
            f' rx="3" fill="{color}"/>'
            f'<text class="turn-label" x="{cx:.3f}" y="{cy + 0.5:.3f}">{label}</text>'
            f'</g>'
        )
    parts.append('<g class="node-layer">' + "".join(node_parts) + "</g>")

    # ── time axis ──────────────────────────────────────────────────────────
    if time_axis:
        # Axis baseline: sits _TIME_AXIS_H/2 below the last lane bottom (tool area)
        axis_y = _MARGIN_TOP + n_lanes * _LANE_STEP + _MARGIN_BOTTOM + _axis_extra // 2
        ax_x1  = float(_MARGIN_LEFT)
        ax_x2  = float(canvas_w - _MARGIN_RIGHT)

        axis_parts: list[str] = []
        axis_parts.append(
            f'<line class="time-axis-line"'
            f' x1="{ax_x1:.1f}" y1="{axis_y}" x2="{ax_x2:.1f}" y2="{axis_y}"/>'
        )

        if _use_timing:
            tick_interval = _nice_time_interval(t_span)
            tick_t = 0.0
            while tick_t <= t_span + tick_interval * 0.01:
                tx = _MARGIN_LEFT + tick_t * _pps
                if tx > ax_x2 + 1:
                    break
                lbl = _fmt_time_s(tick_t)
                axis_parts.append(
                    f'<line class="time-tick"'
                    f' x1="{tx:.2f}" y1="{axis_y}" x2="{tx:.2f}" y2="{axis_y + 5}"/>'
                )
                axis_parts.append(
                    f'<text class="time-label"'
                    f' x="{tx:.2f}" y="{axis_y + 15}">{lbl}</text>'
                )
                tick_t += tick_interval
        else:
            # Equal-slot mode: one small tick per call centre showing start time
            t_run_min = min(c["start_ts"] for c in llm_calls) if llm_calls else 0.0
            for i, c in enumerate(llm_calls):
                tx  = call_cx[i]
                lbl = _fmt_time_s(c["start_ts"] - t_run_min)
                axis_parts.append(
                    f'<line class="time-tick"'
                    f' x1="{tx:.2f}" y1="{axis_y}" x2="{tx:.2f}" y2="{axis_y + 4}"/>'
                )
                axis_parts.append(
                    f'<text class="time-label"'
                    f' x="{tx:.2f}" y="{axis_y + 14}">{lbl}</text>'
                )
        parts.append('<g class="time-axis-layer">' + "".join(axis_parts) + "</g>")

    # ── title ──────────────────────────────────────────────────────────────
    title_esc = _html.escape(title)
    parts.append(
        f'<text class="graph-title" x="{canvas_w / 2:.0f}" y="14">'
        f'{title_esc}</text>'
    )

    # ── inline legend ──────────────────────────────────────────────────────
    legend_parts: list[str] = []
    legend_parts.append(
        f'<line class="legend-sep"'
        f' x1="0" y1="{diagram_h}" x2="{canvas_w}" y2="{diagram_h}"/>'
    )
    swatch_y = diagram_h + (_LEGEND_H - _LEGEND_SWATCH) // 2
    lx = float(_MARGIN_LEFT)
    for agent in agent_order:
        a_idx = agent_idx_map[agent]
        color = _agent_color(a_idx)
        label_text = _html.escape(agent)
        legend_parts.append(
            f'<rect class="legend-swatch"'
            f' x="{lx:.1f}" y="{swatch_y}"'
            f' width="{_LEGEND_SWATCH}" height="{_LEGEND_SWATCH}" rx="2"'
            f' fill="{color}"/>'
            f'<text class="legend-label"'
            f' x="{lx + _LEGEND_SWATCH + 4:.1f}" y="{swatch_y + _LEGEND_SWATCH / 2:.1f}">'
            f'{label_text}</text>'
        )
        lx += _LEGEND_STEP
    parts.append('<g class="legend-layer">' + "".join(legend_parts) + "</g>")

    # ── assemble SVG ───────────────────────────────────────────────────────
    svg_css = _build_svg_css(theme, standalone=standalone)
    inner = "".join(parts)
    svg = (
        f'<svg viewBox="0 0 {canvas_w} {canvas_h}"'
        f' preserveAspectRatio="xMidYMid meet"'
        f' role="img" aria-label="{title_esc}"'
        f' xmlns="http://www.w3.org/2000/svg">'
        f'<style>{svg_css}</style>'
        f'{inner}'
        f'</svg>'
    )

    if fmt == "html":
        return _HTML_WRAPPER.format(title=title_esc, svg=svg, initial_theme=theme)
    return svg

