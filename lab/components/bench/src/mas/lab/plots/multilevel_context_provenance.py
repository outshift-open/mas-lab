#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Multilevel Context Provenance — agent-level context-flow diagram.

Complements the message graph by showing *information flow* rather than
*execution flow*: for each LLM call, which agents (or direct tool calls)
have already contributed to its assembled context.

Layout
------
Same swim-lane structure as the message graph:

* One horizontal row per agent, ordered by first appearance.
* LLM calls as numbered, colour-coded boxes left-to-right.
* **Contributor chips** below each box — one coloured square per agent
  whose output is already in this call's context.  New contributors (not
  present in the same agent's previous call) receive a white ring.
* **Context-flow arrows** — dashed curved arcs from the last box of a
  contributing agent to the receiving call.  Coloured by contributor.
* **Iteration bands** inherited from message_graph.

Context extraction
------------------
Uses the KG call tree (``parent_call_id``):

* Sub-``AgentCall`` children that *completed* before a given ``LLMCall``
  are treated as **delegation** contributors (their output fed back into
  the parent agent's context).
* ``ToolCall`` children that completed before a given ``LLMCall`` are
  **tool-result** contributors (used by agents that invoke tools directly,
  rather than delegating).
* Every call always has a ``self`` contributor (system prompt + task).

Tooltip content (HTML mode)
---------------------------
Hovering a box shows:

* The list of contributing agents at this call, with mechanism labels.
* Output preview for each contributor.
* For delegation contributors, the sub-chain they themselves received.

Usage
-----
Python API::

    from mas.lab.plots.multilevel_context_provenance import plot_multilevel_context_provenance
    from mas.lab.plots.kg_adapter import load_kg

    kg   = load_kg("path/to/kg.json")
    html = plot_multilevel_context_provenance(kg, title="SRE — Context Flow", fmt="html")

CLI::

    mas-lab plot context-flow path/to/kg.json -o flow.html
    mas-lab plot context-flow cognitive-challenges/c4-smoke --format html
"""

import bisect
import html as _html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from mas.lab.plots.kg_adapter import KGView
from mas.lab.plots.message_graph import (
    # Layout constants
    _MARGIN_LEFT, _MARGIN_RIGHT, _MARGIN_TOP, _MARGIN_BOTTOM,
    _LANE_STEP, _SLOT_W, _BOX_H, _BOX_W, _BOX_PAD,
    _TOOL_TICK_H, _TOOL_SIZE, _TOOL_GAP,
    _LEGEND_SWATCH, _LEGEND_STEP, _LEGEND_H,
    # Colour helpers
    _AGENT_PALETTE, _agent_color,
    # Tooltip helpers
    _dur_str, _preview, _tip_attrs,
    # Theme system
    _LIGHT, _DARK, _vars_block, _SVG_CLASS_STYLES, _build_svg_css, _HTML_WRAPPER,
    # Geometry helpers
    _lane_y, _slot_cx, _box_left, _box_right, _box_top,
    # Data helpers
    _extract, _find_root_agent_id, _assign_iterations,
)

__all__ = ["plot_multilevel_context_provenance"]

# ---------------------------------------------------------------------------
# Context-contribution extraction
# ---------------------------------------------------------------------------

def _build_tree(view: KGView) -> dict[str, list[dict]]:
    """Return parent_call_id → list[child record] for all KG nodes."""
    tree: dict[str, list[dict]] = defaultdict(list)
    for ct in view.types():
        for rec in view.query(ct):
            pid = rec.get("parent_call_id") or "__root__"
            tree[pid].append(rec)  # type: ignore[index]
    return dict(tree)


def _extract_contributions(
    view: KGView,
) -> dict[str, list[dict]]:
    """Return ``{llm_call_id: [contrib, ...]}`` for every LLMCall.

    Each contrib dict has:
    ``agent_id``       — originator agent
    ``call_id``        — the AgentCall / ToolCall that contributed
    ``mechanism``      — see taxonomy below
    ``delivery``       — delivery mechanism for delegation (``"tool_call"`` | ``""``)
    ``label``          — display label (tool name, agent name, or ``"system prompt"``)
    ``output_preview`` — first 300 chars of content

    Provenance taxonomy
    -------------------
    ``system``      Static system prompt (instructions, persona).
    ``user_input``  User task/query injected into this agent's context.  For
                    delegated agents this is the query sent by the parent agent.
                    Only present on the *first* LLM call of an AgentCall.
    ``delegation``  Sub-agent response received via tool call.  Has its own
                    recursive provenance tree (``children``).
    ``tool_result`` Direct tool/API call result (non-agent tool).
    ``memory``      Memory recall (future).
    ``skill``       Skill plugin result (future).
    ``hitl``        Human-in-the-loop mid-task input requested by the LLM (future).
    """
    tree = _build_tree(view)
    llm_calls = view.query("LLMCall")  # sorted by start_ts

    # Index all calls by ID for parent-AgentCall lookup
    all_calls_by_id: dict[str, dict] = {}
    for ct in view.types():
        for rec in view.query(ct):
            if rec.get("call_id"):
                all_calls_by_id[rec["call_id"]] = rec

    # Track first LLM call per parent so user_input is injected only once
    first_llm_per_parent: dict[str, str] = {}
    for llm in sorted(llm_calls, key=lambda x: float(x.get("start_ts") or 0)):
        pid = llm.get("parent_call_id") or "__root__"
        if pid not in first_llm_per_parent:
            first_llm_per_parent[pid] = llm["call_id"]

    result: dict[str, list[dict]] = {}
    for llm in llm_calls:
        cid    = llm["call_id"]
        agent  = llm["agent_id"]
        parent = llm.get("parent_call_id")

        # System prompt is always present
        contribs: list[dict] = [{
            "agent_id":       agent,
            "call_id":        None,
            "mechanism":      "system",
            "delivery":       "",
            "label":          "system prompt",
            "output_preview": "(system instructions)",
        }]

        # User task/query — only on the first LLM call of this AgentCall
        if parent and first_llm_per_parent.get(parent) == cid:
            parent_rec = all_calls_by_id.get(parent, {})
            user_q = _preview(parent_rec.get("input") or "", 300)
            if user_q and user_q != "(empty)":
                contribs.append({
                    "agent_id":       agent,
                    "call_id":        None,
                    "mechanism":      "user_input",
                    "delivery":       "",
                    "label":          "user task",
                    "output_preview": user_q,
                })

        if parent:
            siblings = sorted(
                [
                    s for s in tree.get(parent, [])
                    if s.get("end_ts") and s["end_ts"] < llm["start_ts"]
                ],
                key=lambda s: s.get("end_ts", 0),
            )
            for sib in siblings:
                sib_ct = sib.get("call_type")
                if sib_ct == "AgentCall":
                    # Sub-agent response received via tool call
                    contribs.append({
                        "agent_id":       sib["agent_id"],
                        "call_id":        sib["call_id"],
                        "mechanism":      "delegation",
                        "delivery":       "tool_call",
                        "label":          sib["agent_id"],
                        "output_preview": _preview(sib.get("output") or "", 300),
                    })
                elif sib_ct == "ToolCall":
                    tname = sib.get("tool_name") or sib.get("label") or "tool"
                    contribs.append({
                        "agent_id":       agent,
                        "call_id":        sib["call_id"],
                        "mechanism":      "tool_result",
                        "delivery":       "",
                        "label":          tname,
                        "output_preview": _preview(sib.get("output") or "", 200),
                    })

        result[cid] = contribs
    return result


# ---------------------------------------------------------------------------
# Provenance tree builder (recursive, depth-limited)
# ---------------------------------------------------------------------------

_PROV_ASSET = Path(__file__).parent / "assets" / "context_provenance.html"
_EM_DASH = "\u2014"


def _build_provenance_tree(
    llm_calls: list[dict],
    agent_idx_map: dict[str, int],
    contribs: dict[str, list[dict]],
    max_depth: int = 3,
) -> dict[str, list[dict]]:
    """Return ``{llm_call_id: [prov_node, ...]}`` with recursive ``children``.

    Prov-node schema::

        agentId         str   originator agent
        mechanism       str   "system" | "user_input" | "delegation" | "tool_result" | ...
        delivery        str   "tool_call" | "" — delivery mechanism (delegation only)
        label           str   display label
        color           str   hex colour from agent palette
        outputPreview   str   first ~300 chars of content
        children        list  recursive (delegation only, empty for terminal sources)
        transitionCount int   LLM calls survived (delegation only)
    """
    llm_by_id: dict[str, dict] = {c["call_id"]: c for c in llm_calls}
    llm_by_parent: dict[str, list[str]] = defaultdict(list)
    for c in llm_calls:
        pid = c.get("parent_call_id") or "__root__"
        llm_by_parent[pid].append(c["call_id"])

    cache: dict[tuple, list[dict]] = {}

    def _build(call_id: str, depth: int) -> list[dict]:
        key = (call_id, depth)
        if key in cache:
            return cache[key]
        nodes: list[dict] = []
        for ct in contribs.get(call_id, []):
            ag   = ct["agent_id"]
            mech = ct["mechanism"]
            node: dict = {
                "agentId":       ag,
                "mechanism":     mech,
                "delivery":      ct.get("delivery") or "",
                "label":         ct["label"],
                "color":         _agent_color(agent_idx_map.get(ag, 0)),
                "outputPreview": ct.get("output_preview") or "",
                "children":      [],
            }
            if mech == "delegation" and depth > 1:
                agent_call_id = ct.get("call_id")
                if agent_call_id:
                    child_ids  = llm_by_parent.get(agent_call_id, [])
                    child_llms = [llm_by_id[cid] for cid in child_ids if cid in llm_by_id]
                    node["transitionCount"] = len(child_llms)
                    if child_llms:
                        last = max(child_llms, key=lambda x: float(x.get("start_ts") or 0))
                        node["children"] = _build(last["call_id"], depth - 1)
            nodes.append(node)
        cache[key] = nodes
        return nodes

    return {cid: _build(cid, max_depth) for cid in contribs}


# ---------------------------------------------------------------------------
# SVG rendering helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def plot_multilevel_context_provenance(
    kg: dict,
    title: str = "Context Provenance",
    fmt: str = "html",
    theme: str = "auto",
    hover: bool = True,
) -> str:
    """Render a multilevel context-provenance diagram.

    Args:
        kg:     Knowledge-graph dict (from :func:`~mas.lab.plots.kg_adapter.load_kg`).
        title:  Diagram title.
        fmt:    ``"html"`` (default) or ``"svg"``.
        theme:  ``"auto"`` (default), ``"light\"``, or ``"dark"``.
        hover:  When ``True`` (default) attach tooltip data to interactive elements.
    """
    standalone = (fmt != "html")
    view = KGView.from_kg(kg)
    llm_calls, tool_by_llm = _extract(view)

    if not llm_calls:
        return (
            '<svg viewBox="0 0 320 60" xmlns="http://www.w3.org/2000/svg">'
            '<text x="160" y="35" text-anchor="middle" font-family="sans-serif"'
            ' font-size="13" fill="#666">No LLM calls found in this run.</text>'
            "</svg>"
        )

    contribs = _extract_contributions(view)

    root_agent_id = _find_root_agent_id(view)
    iterations    = _assign_iterations(llm_calls, root_agent_id)

    # Ordered agent list (first-appearance order)
    agent_order: list[str] = []
    seen_agents: set[str]  = set()
    for c in llm_calls:
        aid = c["agent_id"] or "?"
        if aid not in seen_agents:
            seen_agents.add(aid)
            agent_order.append(aid)

    agent_idx_map: dict[str, int] = {a: i for i, a in enumerate(agent_order)}
    n_lanes  = len(agent_order)
    n_calls  = len(llm_calls)

    # Build provenance tree now that agent_idx_map is available
    if hover:
        prov_tree = _build_provenance_tree(llm_calls, agent_idx_map, contribs)
    else:
        prov_tree = {}

    canvas_w  = _MARGIN_LEFT + n_calls * _SLOT_W + _MARGIN_RIGHT
    canvas_h  = _MARGIN_TOP + n_lanes * _LANE_STEP + _MARGIN_BOTTOM + _LEGEND_H
    diagram_h = canvas_h - _LEGEND_H

    parts: list[str] = []

    # ── background ──────────────────────────────────────────────────────────
    parts.append('<rect class="mg-bg" width="100%" height="100%"/>')

    # ── defs (arrow marker) ───────────────────────────────────────────────
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
        x_min = _slot_cx(min(indices)) - _SLOT_W / 2
        x_max = _slot_cx(max(indices)) + _SLOT_W / 2
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
        lane_parts.append(
            f'<line class="lane-line"'
            f' x1="{line_x1}" y1="{y}" x2="{line_x2:.1f}" y2="{y}"/>'
        )
        lane_parts.append(
            f'<text class="lane-label" x="{_MARGIN_LEFT - 14}" y="{y}">'
            f'{_html.escape(agent)}</text>'
        )
    parts.append('<g class="lane-layer">' + "".join(lane_parts) + "</g>")

    # ── chronological flow edges (same as message_graph) ─────────────────────
    edge_parts: list[str] = []
    for i in range(n_calls - 1):
        c_i = llm_calls[i]
        c_j = llm_calls[i + 1]
        aid_i, aid_j = c_i["agent_id"] or "", c_j["agent_id"] or ""
        cy_i = _lane_y(agent_idx_map, aid_i)
        cy_j = _lane_y(agent_idx_map, aid_j)
        right_i = _box_right(i)
        left_j  = _box_left(i + 1)
        cx_j    = _slot_cx(i + 1)
        top_j   = _box_top(agent_idx_map, aid_j)

        if cy_i == cy_j:
            edge_parts.append(
                f'<path class="graph-edge"'
                f' d="M {right_i:.3f} {cy_i} L {left_j:.3f} {cy_i}"/>'
            )
        elif cy_j > cy_i:
            edge_parts.append(
                f'<path class="graph-edge"'
                f' d="M {right_i:.3f} {cy_i} L {cx_j:.3f} {cy_i}"/>'
            )
            edge_parts.append(
                f'<path class="graph-edge" marker-end="url(#mg-arrow)"'
                f' d="M {cx_j:.3f} {cy_i} L {cx_j:.3f} {top_j - 1:.3f}"/>'
            )
        else:
            bend_x = right_i + 2.0
            edge_parts.append(
                f'<path class="graph-edge" marker-end="url(#mg-arrow)"'
                f' d="M {right_i:.3f} {cy_i}'
                f' L {bend_x:.3f} {cy_i}'
                f' L {bend_x:.3f} {cy_j:.3f}"/>'
            )
            edge_parts.append(
                f'<path class="graph-edge"'
                f' d="M {bend_x:.3f} {cy_j} L {left_j:.3f} {cy_j}"/>'
            )
    parts.append('<g class="edge-layer">' + "".join(edge_parts) + "</g>")

    # ── tool-call squares ───────────────────────────────────────────────────────────────────────────
    tool_parts: list[str] = []
    for i, c in enumerate(llm_calls):
        cid_t   = c["call_id"]
        tools_t = tool_by_llm.get(cid_t, [])
        if not tools_t:
            continue
        n_tools  = len(tools_t)
        cx_t     = _slot_cx(i)
        cy_t     = _lane_y(agent_idx_map, c["agent_id"] or "")
        tick_y1  = cy_t + _BOX_H / 2
        tick_y2  = tick_y1 + _TOOL_TICK_H
        tool_parts.append(
            f'<line class="tool-tick"'
            f' x1="{cx_t:.3f}" y1="{tick_y1}" x2="{cx_t:.3f}" y2="{tick_y2}"/>'
        )
        total_w  = n_tools * _TOOL_SIZE + (n_tools - 1) * _TOOL_GAP
        start_x  = cx_t - total_w / 2
        for j, t in enumerate(tools_t):
            tx      = start_x + j * (_TOOL_SIZE + _TOOL_GAP)
            _tname  = t.get("tool_name") or t.get("label") or f"tool-{j + 1}"
            _tdur   = _dur_str(t["start_ts"], t.get("end_ts"))
            _tbody  = (
                f"Agent: {t.get('agent_id', '')}\n"
                f"Duration: {_tdur}\n"
                f"\nInput:\n{_preview(t.get('input'), 220)}\n"
                f"\nOutput:\n{_preview(t.get('output'), 220)}"
            )
            _ta_t   = _tip_attrs(_tname, _tbody) if hover else ""
            _ttitle = (
                f'<title>{_html.escape(_tname)} \u00b7 {_tdur}</title>'
                if standalone and hover else ''
            )
            tool_parts.append(
                f'<g{_ta_t}>{_ttitle}'
                f'<rect class="tool-square"'
                f' x="{tx:.3f}" y="{tick_y2}"'
                f' width="{_TOOL_SIZE}" height="{_TOOL_SIZE}"/>'
                f'</g>'
            )
    parts.append('<g class="tool-layer">' + "".join(tool_parts) + "</g>")

    # ── LLM-call boxes ────────────────────────────────────────────────────────────────────────────────
    node_parts: list[str] = []
    for i, c in enumerate(llm_calls):
        aid    = c["agent_id"] or ""
        a_idx  = agent_idx_map.get(aid, 0)
        color  = _agent_color(a_idx)
        bx     = _box_left(i)
        cy     = _lane_y(agent_idx_map, aid)
        by     = cy - _BOX_H / 2
        cx     = _slot_cx(i)
        cid    = c.get("call_id")
        label  = str(i + 1)
        if hover:
            call_contribs = contribs.get(cid, [])
            user_in = [ct for ct in call_contribs if ct["mechanism"] == "user_input"]
            deleg   = [ct for ct in call_contribs if ct["mechanism"] == "delegation"]
            tools   = [ct for ct in call_contribs if ct["mechanism"] == "tool_result"]
            body_lines = [
                f"Model:    {c.get('model') or _EM_DASH}",
                f"Duration: {_dur_str(c['start_ts'], c.get('end_ts'))}",
                f"Call:     {(cid or '')[:36]}",
                "",
                f"Context ({len(deleg)} delegations, {len(tools)} tools"
                + (f", user input" if user_in else "") + "):",
            ]
            if user_in:
                body_lines.append(f"  \u2022 [user_input] {_preview(user_in[0].get('output_preview'), 80)}")
            for ct in deleg:
                body_lines.append(f"  \u2022 [delegation] {ct['agent_id']} via tool call")
                body_lines.append(f"    {_preview(ct.get('output_preview',''), 120)}")
            for ct in tools:
                body_lines.append(f"  \u2022 [tool_result] {ct['label']}")
            body_lines += ["", "Output:", _preview(c.get("output"), 300)]
            tip_lbl  = f"{aid} \u2014 Turn {i + 1}"
            tip_body = "\n".join(body_lines)
            ta       = _tip_attrs(tip_lbl, tip_body)
            if standalone:
                title_txt = tip_lbl
                if deleg or tools or user_in:
                    parts_txt = []
                    if user_in:
                        parts_txt.append("user_input")
                    parts_txt += [f"delegation:{ct['agent_id']}" for ct in deleg]
                    parts_txt += [f"tool:{ct['label']}" for ct in tools]
                    title_txt += "\n" + ", ".join(parts_txt)
                t_title = f'<title>{_html.escape(title_txt)}</title>'
            else:
                t_title = ""
            prov_nodes = prov_tree.get(cid, [])
            prov_json  = _html.escape(
                json.dumps(prov_nodes, ensure_ascii=False, separators=(",", ":")),
                quote=True,
            )
            data_prov = f' data-prov="{prov_json}"'
            data_turn = f' data-turn="{i + 1}"'
        else:
            ta, t_title = "", ""
            data_prov = data_turn = ""

        node_parts.append(
            f'<g class="turn-node"{ta}'
            f' data-agent="{_html.escape(aid)}" data-color="{color}"'
            f'{data_turn}{data_prov}>'
            f'{t_title}'
            f'<rect class="turn-rect"'
            f' x="{bx:.3f}" y="{by:.3f}"'
            f' width="{_BOX_W}" height="{_BOX_H}"'
            f' rx="3" fill="{color}"/>'
            f'<text class="turn-label" x="{cx:.3f}" y="{cy + 0.5:.3f}">{label}</text>'
            f'</g>'
        )

    parts.append('<g class="node-layer">' + "".join(node_parts) + "</g>")

    # ── title ──────────────────────────────────────────────────────────────
    title_esc = _html.escape(title)
    parts.append(
        f'<text class="graph-title" x="{canvas_w / 2:.0f}" y="14">'
        f'{title_esc}</text>'
    )

    # ── inline legend (agents) ─────────────────────────────────────────────
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
        legend_parts.append(
            f'<rect class="legend-swatch"'
            f' x="{lx:.1f}" y="{swatch_y}"'
            f' width="{_LEGEND_SWATCH}" height="{_LEGEND_SWATCH}" rx="2"'
            f' fill="{color}"/>'
            f'<text class="legend-label"'
            f' x="{lx + _LEGEND_SWATCH + 4:.1f}" y="{swatch_y + _LEGEND_SWATCH / 2:.1f}">'
            f'{_html.escape(agent)}</text>'
        )
        lx += _LEGEND_STEP
    parts.append('<g class="legend-layer">' + "".join(legend_parts) + "</g>")

    # ── assemble SVG ───────────────────────────────────────────────────────
    svg_css = _build_svg_css(theme, standalone=standalone)
    if hover:
        svg_css += (
            "\n  .turn-node { cursor: pointer; }"
            "\n  .turn-node:hover .turn-rect { stroke: rgba(255,255,255,.65); stroke-width: 2; }"
        )
    inner   = "".join(parts)
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
        if _PROV_ASSET.exists():
            tmpl = _PROV_ASSET.read_text(encoding="utf-8")
            return (
                tmpl
                .replace("{title}", title_esc)
                .replace("{svg}", svg)
                .replace("{initial_theme}", theme)
            )
        return _HTML_WRAPPER.format(title=title_esc, svg=svg, initial_theme=theme)
    return svg


# ---------------------------------------------------------------------------
# Extra CSS (none needed — all styles shared with message_graph)
# ---------------------------------------------------------------------------
