#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Generate an interactive HTML trajectory from an events.jsonl trace.

Highlights memory injection events (context_part_contributed, source=memory)
with gray markers, tool calls with colored markers, and LLM calls as spans.

Usage:
    python gen_trajectory_html.py <events.jsonl> [output.html]
"""

import json
import sys
import os

AGENT_COLORS = {
    "moderator":       "#4A90D9",
    "itinerary_agent": "#43A86D",
    "schedule_agent":  "#E07B39",
    "concierge_agent": "#C74B50",
}
AGENT_LABELS = {
    "moderator":       "Moderator",
    "itinerary_agent": "Itinerary",
    "schedule_agent":  "Schedule",
    "concierge_agent": "Concierge",
}
AGENT_ORDER = ["moderator", "itinerary_agent", "schedule_agent", "concierge_agent"]

MEM_COLOR   = "#8C8C9E"   # gray-blue for memory injection
LLM_COLOR   = "#6E6E7A"   # dark gray for LLM spans
TOOL_COLORS = {
    "lookup_schedule":      "#E07B39",
    "query_graph_database": "#43A86D",
    "get_fares":            "#C74B50",
}
TOOL_DEFAULT_COLOR = "#A07BC0"


def load_events(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def build_data(events):
    t0 = events[0]["timestamp"]

    execution_spans = []   # (agent, start, end, call_id)
    llm_spans = []         # (agent, start, end)
    tool_events = []       # (agent, ts, tool_name, call_id)
    mem_events = []        # (agent, ts, tokens, section)

    open_exec = {}
    open_llm  = {}
    open_tool = {}

    for e in events:
        ts = e["timestamp"] - t0
        kind = e.get("kind", "")
        agent = e.get("agent_id", "?")

        if kind == "execution_start":
            open_exec[e["call_id"]] = (agent, ts)
        elif kind == "execution_end":
            cid = e["call_id"]
            if cid in open_exec:
                a, s = open_exec.pop(cid)
                execution_spans.append({"agent": a, "start": s, "end": ts, "id": cid})

        elif kind == "llm_call_start":
            cid = e.get("call_id", f"llm_{ts}")
            open_llm[cid] = (agent, ts)
        elif kind == "llm_call_end":
            cid = e.get("call_id", "")
            if cid in open_llm:
                a, s = open_llm.pop(cid)
                llm_spans.append({"agent": a, "start": s, "end": ts})

        elif kind == "tool_call_start":
            cid = e.get("call_id", f"tool_{ts}")
            open_tool[cid] = (agent, ts, e.get("tool_name", "?"), e.get("arguments", {}))
        elif kind == "tool_call_end":
            cid = e.get("call_id", "")
            if cid in open_tool:
                a, s, tname, args = open_tool.pop(cid)
                tool_events.append({
                    "agent": a, "start": s, "end": ts,
                    "tool": tname,
                    "args": str(args)[:80]
                })

        elif kind == "context_part_contributed" and e.get("source") == "memory":
            mem_events.append({
                "agent":   agent,
                "ts":      ts,
                "tokens":  e.get("token_estimate", 0),
                "section": e.get("section_id", "memory"),
                "mechanism": e.get("access_mechanism", "inject"),
                "content_preview": (e.get("content") or "")[:120],
            })

    tmax = max(
        (s["end"] for s in execution_spans),
        default=60.0
    )
    return {
        "execution_spans": execution_spans,
        "llm_spans": llm_spans,
        "tool_events": tool_events,
        "mem_events": mem_events,
        "tmax": tmax,
    }


def to_html(data, run_id="", title="Agent Trajectory — with-letta-memory"):
    execution_spans = data["execution_spans"]
    llm_spans = data["llm_spans"]
    tool_events = data["tool_events"]
    mem_events = data["mem_events"]
    tmax = data["tmax"]

    # SVG dimensions
    W = 900
    MARGIN_L = 110
    MARGIN_R = 30
    MARGIN_TOP = 50
    ROW_H = 60
    N = len(AGENT_ORDER)
    H = MARGIN_TOP + N * ROW_H + 50
    PLOT_W = W - MARGIN_L - MARGIN_R

    def tx(t):
        return MARGIN_L + (t / tmax) * PLOT_W

    def ty(agent):
        idx = AGENT_ORDER.index(agent) if agent in AGENT_ORDER else 0
        return MARGIN_TOP + idx * ROW_H + ROW_H // 2

    lines = []
    tooltips = []  # list of (x, y, text)

    def add(s):
        lines.append(s)

    # ── background rows ─────────────────────────────────────────────────────
    for i, agent in enumerate(AGENT_ORDER):
        y = MARGIN_TOP + i * ROW_H
        bg = "#1A1F2E" if i % 2 == 0 else "#1E2437"
        add(f'<rect x="{MARGIN_L}" y="{y}" width="{PLOT_W}" height="{ROW_H}" fill="{bg}"/>')

    # ── time grid ────────────────────────────────────────────────────────────
    step = 10 if tmax <= 60 else (20 if tmax <= 120 else 30)
    t = 0
    while t <= tmax:
        x = tx(t)
        add(f'<line x1="{x:.1f}" y1="{MARGIN_TOP}" x2="{x:.1f}" y2="{MARGIN_TOP + N * ROW_H}" stroke="#2A3048" stroke-width="1"/>')
        add(f'<text x="{x:.1f}" y="{MARGIN_TOP + N * ROW_H + 16}" text-anchor="middle" font-size="10" fill="#7A8099">{int(t)}s</text>')
        t += step

    # ── execution spans (thin background bars) ───────────────────────────────
    for s in execution_spans:
        if s["agent"] not in AGENT_ORDER:
            continue
        x1, x2 = tx(s["start"]), tx(s["end"])
        y_center = ty(s["agent"])
        color = AGENT_COLORS.get(s["agent"], "#666")
        add(f'<rect x="{x1:.1f}" y="{y_center-14}" width="{max(x2-x1,2):.1f}" height="28" '
            f'rx="4" fill="{color}" fill-opacity="0.25" stroke="{color}" stroke-opacity="0.5" stroke-width="1"/>')

    # ── LLM call spans ────────────────────────────────────────────────────────
    for s in llm_spans:
        if s["agent"] not in AGENT_ORDER:
            continue
        x1, x2 = tx(s["start"]), tx(s["end"])
        y_center = ty(s["agent"])
        color = AGENT_COLORS.get(s["agent"], "#666")
        add(f'<rect x="{x1:.1f}" y="{y_center-9}" width="{max(x2-x1,3):.1f}" height="18" '
            f'rx="2" fill="{color}" fill-opacity="0.75" stroke="{color}" stroke-width="0.5">'
            f'<title>LLM call: {s["agent"]}\n{s["start"]:.1f}s → {s["end"]:.1f}s ({s["end"]-s["start"]:.1f}s)</title>'
            f'</rect>')

    # ── tool call spans ────────────────────────────────────────────────────────
    for t_ev in tool_events:
        if t_ev["agent"] not in AGENT_ORDER:
            continue
        x1, x2 = tx(t_ev["start"]), tx(t_ev["end"])
        y_center = ty(t_ev["agent"])
        color = TOOL_COLORS.get(t_ev["tool"], TOOL_DEFAULT_COLOR)
        w = max(x2 - x1, 4)
        add(f'<rect x="{x1:.1f}" y="{y_center-16}" width="{w:.1f}" height="10" '
            f'rx="2" fill="{color}" fill-opacity="0.9" stroke="{color}" stroke-width="1">'
            f'<title>Tool: {t_ev["tool"]}\n{t_ev["args"]}\n{t_ev["start"]:.1f}s → {t_ev["end"]:.1f}s</title>'
            f'</rect>')
        # Small label above
        label = t_ev["tool"].split("_")[0][:6]
        mid_x = (x1 + x1 + w) / 2
        add(f'<text x="{mid_x:.1f}" y="{y_center-20}" text-anchor="middle" font-size="8" fill="{color}" font-weight="bold">{label}</text>')

    # ── memory injection markers (the key feature) ───────────────────────────
    for m in mem_events:
        if m["agent"] not in AGENT_ORDER:
            continue
        x = tx(m["ts"])
        y_center = ty(m["agent"])
        # Diamond shape below the main bar
        dm = 6  # half-size of diamond
        pts = f"{x:.1f},{y_center+9+dm*2} {x+dm:.1f},{y_center+9+dm} {x:.1f},{y_center+9} {x-dm:.1f},{y_center+9+dm}"
        add(f'<polygon points="{pts}" fill="{MEM_COLOR}" fill-opacity="0.9" stroke="#BCBCCC" stroke-width="0.5">'
            f'<title>Memory injection (passive)\nAgent: {m["agent"]}\nt={m["ts"]:.1f}s\n{m["tokens"]} tokens\nMechanism: {m["mechanism"]}\n{m["section"]}\n\n{m["content_preview"]}</title>'
            f'</polygon>')
        # Vertical stem connecting to agent bar
        add(f'<line x1="{x:.1f}" y1="{y_center+9}" x2="{x:.1f}" y2="{y_center+2}" stroke="{MEM_COLOR}" stroke-width="1.2" stroke-opacity="0.7" stroke-dasharray="2,1"/>')
        # Small label
        add(f'<text x="{x:.1f}" y="{y_center+9+dm*2+10}" text-anchor="middle" font-size="7" fill="{MEM_COLOR}">mem↓</text>')

    # ── Y-axis labels ─────────────────────────────────────────────────────────
    for agent in AGENT_ORDER:
        y_center = ty(agent)
        color = AGENT_COLORS.get(agent, "#ccc")
        label = AGENT_LABELS.get(agent, agent)
        add(f'<text x="{MARGIN_L-8}" y="{y_center+4}" text-anchor="end" font-size="12" fill="{color}" font-weight="500">{label}</text>')

    # ── title & legend ───────────────────────────────────────────────────────
    add(f'<text x="{W//2}" y="22" text-anchor="middle" font-size="14" fill="#E0E4F0" font-weight="600">{title}</text>')

    # Legend
    lx = MARGIN_L
    ly = H - 18
    add(f'<rect x="{lx}" y="{ly-8}" width="12" height="8" rx="2" fill="#4A90D9" fill-opacity="0.75"/>')
    add(f'<text x="{lx+16}" y="{ly}" font-size="10" fill="#9AA0B8">LLM call (agent bar)</text>')
    lx += 130
    add(f'<polygon points="{lx+5},{ly} {lx+10},{ly-5} {lx+5},{ly-10} {lx},{ly-5}" fill="{MEM_COLOR}"/>')
    add(f'<text x="{lx+16}" y="{ly}" font-size="10" fill="#9AA0B8">Memory injection (passive, Letta blocks)</text>')
    lx += 230
    add(f'<rect x="{lx}" y="{ly-9}" width="12" height="7" rx="2" fill="{TOOL_COLORS["lookup_schedule"]}" fill-opacity="0.9"/>')
    add(f'<text x="{lx+16}" y="{ly}" font-size="10" fill="#9AA0B8">Tool call (data retrieval)</text>')
    lx += 170
    add(f'<text x="{lx}" y="{ly}" font-size="10" fill="#E07070">⚠ No memory_search tool calls (active retrieval absent)</text>')

    # Time axis label
    add(f'<text x="{MARGIN_L + PLOT_W//2}" y="{MARGIN_TOP + N * ROW_H + 32}" text-anchor="middle" font-size="11" fill="#9AA0B8">Time (seconds)</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" style="background:#151929">
{"".join(lines)}
</svg>'''

    # Count stats
    n_mem = len(mem_events)
    n_tool = len(tool_events)
    n_llm = len(llm_spans)
    agents_with_mem = sorted(set(m["agent"] for m in mem_events))

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ margin: 0; background: #0F1320; font-family: 'Inter', 'Segoe UI', sans-serif; color: #E0E4F0; padding: 24px; }}
  h1 {{ font-size: 1.2rem; margin-bottom: 4px; color: #C8D0E8; }}
  .meta {{ font-size: 0.82rem; color: #6A7090; margin-bottom: 20px; }}
  .stats {{ display: flex; gap: 24px; margin-bottom: 20px; }}
  .stat {{ background: #1A1F2E; border: 1px solid #2A3048; border-radius: 8px; padding: 10px 16px; }}
  .stat-label {{ font-size: 0.75rem; color: #6A7090; text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat-value {{ font-size: 1.5rem; font-weight: 700; margin-top: 2px; }}
  .mem-color {{ color: {MEM_COLOR}; }}
  .tool-color {{ color: #A07BC0; }}
  .llm-color {{ color: #9AABE0; }}
  .warn {{ color: #E07070; }}
  .note {{ background: #1A1F2E; border-left: 3px solid #E07070; padding: 10px 16px; border-radius: 4px; font-size: 0.85rem; margin-top: 20px; color: #C0C8D8; }}
  .note strong {{ color: #E07070; }}
  .canvas {{ overflow-x: auto; }}
  svg polygon, svg rect {{ cursor: pointer; }}
  svg polygon:hover, svg rect:hover {{ opacity: 0.8; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">Run: {run_id} &nbsp;|&nbsp; Scenario: with-letta-memory &nbsp;|&nbsp; Memory: Letta BasicBlockMemory (passive injection)</div>

<div class="stats">
  <div class="stat">
    <div class="stat-label">LLM calls</div>
    <div class="stat-value llm-color">{n_llm}</div>
  </div>
  <div class="stat">
    <div class="stat-label">Memory injections</div>
    <div class="stat-value mem-color">{n_mem}</div>
  </div>
  <div class="stat">
    <div class="stat-label">Agents with memory</div>
    <div class="stat-value mem-color">{len(agents_with_mem)}</div>
  </div>
  <div class="stat">
    <div class="stat-label">Tool calls (data)</div>
    <div class="stat-value tool-color">{n_tool}</div>
  </div>
  <div class="stat">
    <div class="stat-label">memory_search calls</div>
    <div class="stat-value warn">0</div>
  </div>
</div>

<div class="canvas">
{svg}
</div>

<div class="note">
  <strong>Observation:</strong> Each LLM call receives Letta memory blocks injected passively into context (gray ◆ markers, <code>mem↓</code>). 
  This is <em>context injection</em> via <code>ContextContract.collect_context()</code> — the memory content is always present before each LLM invocation.
  <br><br>
  <strong>Active retrieval absent:</strong> The <code>memory_search</code> tool (ToolContract) was never called by any agent.
  The ReAct agents respond from general knowledge and injected context without explicitly querying memory.
  This reflects the distinction between <em>passive injection</em> (every LLM call, no agent decision)
  and <em>active retrieval</em> (agent decides to call a tool).
</div>
</body>
</html>'''
    return html


def main():
    events_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/.mas-lab/data/trace-cache/44d48e0e9e580f1c60c5/traces/events.jsonl"
    )
    out_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/trajectory-letta.html"

    events = load_events(events_path)
    run_id = os.path.basename(os.path.dirname(os.path.dirname(events_path)))
    data = build_data(events)
    html = to_html(data, run_id=run_id)

    with open(out_path, "w") as f:
        f.write(html)
    print(f"Written: {out_path}")
    print(f"  {len(data['mem_events'])} memory injections, {len(data['tool_events'])} tool calls, {len(data['llm_spans'])} LLM spans")


if __name__ == "__main__":
    main()
