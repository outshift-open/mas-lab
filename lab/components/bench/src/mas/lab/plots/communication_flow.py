#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""CommunicationFlowPlotter — agent-to-agent communication flow diagram.

Produces a directed graph where:

* **Nodes** are agents (moderator, schedule_agent, …)
* **Edges** are routing events between agents, labelled with the delegated task
  and annotated with the round-trip latency

The output is a self-contained dark-themed HTML page using D3 force-directed
layout (``fmt="html"``, default) or a plain Mermaid flowchart string
(``fmt="mermaid"``).

Usage
-----
Direct API::

    from mas.lab.plots.communication_flow import plot_communication_flow
    html = plot_communication_flow(events, fmt="html")

mas-lab CLI::

    mas-lab plot communication-flow runs/.../events.jsonl -o flow.html

Pipeline YAML::

    - name: flow
      type: processor
      processor: communication-flow-plotter
      depends_on: [normalize]
      config:
        fmt: html
        output: reports/flow.html
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from mas.lab.processor import Processor, register
from mas.lab.artifacts import Trajectory, PlotFile


# ---------------------------------------------------------------------------
# Graph extraction from events
# ---------------------------------------------------------------------------

def _extract_communication_graph(events: list[dict]) -> dict:
    """Build a communication graph from routing / execution events.

    Returns a dict with:
        agents  : {agent_id: {"total_delegations_out": int,
                              "total_delegations_in":  int,
                              "llm_calls": int, "tool_calls": int}}
        edges   : [{"source": str, "target": str, "task": str,
                    "latency_ms": float, "count": int}, …]
        session : {"query": str, "final_output": str}
    """
    agents: dict[str, dict] = {}
    # edges keyed by (source, target) → list of {task, latency_ms}
    raw_edges: dict[tuple, list[dict]] = defaultdict(list)

    # Track active routing: correlation_id → {source, target, ts, task}
    pending_routing: dict[str, dict] = {}

    # Track agents from execution events
    for ev in sorted(events, key=lambda e: float(e.get("timestamp") or 0)):
        kind    = ev.get("kind", "")
        agent   = ev.get("agent_id") or ""

        if agent and agent not in agents:
            agents[agent] = {
                "total_delegations_out": 0,
                "total_delegations_in":  0,
                "llm_calls":   0,
                "tool_calls":  0,
            }

        if kind == "llm_call_end" and agent:
            agents.setdefault(agent, defaultdict(int))["llm_calls"] += 1  # type: ignore[arg-type]

        if kind == "tool_call_end" and agent:
            agents.setdefault(agent, defaultdict(int))["tool_calls"] += 1  # type: ignore[arg-type]

        if kind == "routing":
            src    = ev.get("source_agent_id") or ev.get("agent_id") or ""
            tgt    = ev.get("target_agent_id") or ""
            task   = str(ev.get("task") or ev.get("input") or "")[:120]
            cid    = ev.get("correlation_id") or ""
            ts     = float(ev.get("timestamp") or 0)
            if src:
                agents.setdefault(src, defaultdict(int))["total_delegations_out"] += 1  # type: ignore[arg-type]
            if tgt:
                agents.setdefault(tgt, defaultdict(int))["total_delegations_in"]  += 1  # type: ignore[arg-type]
            if cid:
                pending_routing[cid] = {"source": src, "target": tgt,
                                        "task": task, "ts": ts}
            else:
                raw_edges[(src, tgt)].append({"task": task, "latency_ms": 0.0})

        if kind == "routing_result":
            cid = ev.get("correlation_id") or ""
            ts  = float(ev.get("timestamp") or 0)
            if cid in pending_routing:
                pr  = pending_routing.pop(cid)
                lat = max(0.0, (ts - pr["ts"]) * 1000)
                raw_edges[(pr["source"], pr["target"])].append(
                    {"task": pr["task"], "latency_ms": lat}
                )

    # Flush pending routing events that never received a routing_result
    for pr in pending_routing.values():
        raw_edges[(pr["source"], pr["target"])].append(
            {"task": pr["task"], "latency_ms": 0.0}
        )

    # Aggregate edges
    edges: list[dict] = []
    for (src, tgt), items in raw_edges.items():
        edges.append({
            "source":     src,
            "target":     tgt,
            "task":       items[0]["task"] if len(items) == 1 else f"{items[0]['task'][:60]}…",
            "latency_ms": round(sum(i["latency_ms"] for i in items) / len(items), 1),
            "count":      len(items),
        })

    # Extract session info
    query  = ""
    output = ""
    for ev in sorted(events, key=lambda e: float(e.get("timestamp") or 0)):
        if ev.get("kind") == "execution_start" and ev.get("input") and not query:
            query = str(ev["input"])[:300]
        if ev.get("kind") == "execution_end" and ev.get("output"):
            output = str(ev["output"])[:300]

    return {
        "agents":  {k: dict(v) for k, v in agents.items()},
        "edges":   edges,
        "session": {"query": query, "final_output": output},
    }


# ---------------------------------------------------------------------------
# HTML renderer (D3 force-directed)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #12181f; color: #e8eaf6; font-family: 'JetBrains Mono',monospace,sans-serif; }}
  h1   {{ margin: 0; padding: 16px 24px 8px; font-size: 16px; color: #7ecfff; letter-spacing: .06em; }}
  #graph {{ width: 100vw; height: calc(100vh - 56px); }}
  .node circle {{ stroke-width: 2; cursor: pointer; }}
  .node text   {{ font-size: 12px; fill: #e8eaf6; pointer-events: none; }}
  .link        {{ stroke-opacity: .7; }}
  .link-label  {{ font-size: 10px; fill: #a0b0c0; pointer-events: none; }}
  .tooltip     {{ position:absolute; background:#1c2733; border:1px solid #2e3d4f;
                  border-radius:6px; padding:8px 12px; font-size:11px; max-width:320px;
                  pointer-events:none; opacity:0; transition:opacity .15s; line-height:1.5; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div id="graph"></div>
<div class="tooltip" id="tip"></div>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const DATA = {data_json};

const w = window.innerWidth, h = window.innerHeight - 56;
const svg = d3.select("#graph").append("svg")
    .attr("width", w).attr("height", h);

const defs = svg.append("defs");
defs.append("marker").attr("id","arrow").attr("viewBox","0 -5 10 10")
    .attr("refX",24).attr("refY",0).attr("markerWidth",6).attr("markerHeight",6)
    .attr("orient","auto")
  .append("path").attr("d","M0,-5L10,0L0,5").attr("fill","#4fc3f7");

const PAL = ["#4fc3f7","#81c784","#ffb74d","#f48fb1","#ce93d8","#80deea"];
const agentIds = Object.keys(DATA.agents);
const color = d => PAL[agentIds.indexOf(d) % PAL.length];

const nodes = agentIds.map(id => ({{
  id, ...DATA.agents[id]
}}));
const links = DATA.edges.map(e => ({{ ...e, source: e.source, target: e.target }}));

const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id).distance(200).strength(0.6))
  .force("charge", d3.forceManyBody().strength(-600))
  .force("center", d3.forceCenter(w/2, h/2))
  .force("collision", d3.forceCollide(60));

const link = svg.append("g").selectAll("line").data(links).join("line")
  .attr("class","link")
  .attr("stroke", d => "#4fc3f7")
  .attr("stroke-width", d => Math.min(6, 1 + d.count * 1.5))
  .attr("marker-end","url(#arrow)");

const linkLabel = svg.append("g").selectAll("text").data(links).join("text")
  .attr("class","link-label")
  .text(d => d.latency_ms > 0 ? `${{d.latency_ms}}ms` : "");

const node = svg.append("g").selectAll("g").data(nodes).join("g")
  .attr("class","node")
  .call(d3.drag()
    .on("start", (e,d) => {{ if (!e.active) sim.alphaTarget(.3).restart(); d.fx=d.x; d.fy=d.y; }})
    .on("drag",  (e,d) => {{ d.fx=e.x; d.fy=e.y; }})
    .on("end",   (e,d) => {{ if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }}));

node.append("circle").attr("r", d => 22 + (d.llm_calls||0)*3)
  .attr("fill", d => color(d.id) + "33")
  .attr("stroke", d => color(d.id));

node.append("text").attr("dy","0.35em").attr("text-anchor","middle")
  .style("fill", d => color(d.id))
  .style("font-size","11px").style("font-weight","bold")
  .text(d => d.id.split(".").pop().substring(0,16));

const tip = document.getElementById("tip");
node.on("mouseover", (e, d) => {{
  const rows = [
    `<b>${{d.id}}</b>`,
    `LLM calls: ${{d.llm_calls||0}}`,
    `Tool calls: ${{d.tool_calls||0}}`,
    `Delegations out: ${{d.total_delegations_out||0}}`,
    `Delegations in:  ${{d.total_delegations_in||0}}`,
  ];
  tip.innerHTML = rows.join("<br>");
  tip.style.opacity = "1";
  tip.style.left = (e.pageX+12)+"px";
  tip.style.top  = (e.pageY-28)+"px";
}}).on("mousemove", e => {{
  tip.style.left=(e.pageX+12)+"px"; tip.style.top=(e.pageY-28)+"px";
}}).on("mouseout",()=>{{ tip.style.opacity="0"; }});

link.on("mouseover", (e, d) => {{
  tip.innerHTML = `<b>${{d.source.id}} → ${{d.target.id}}</b><br>Task: ${{d.task}}<br>Count: ${{d.count}}   Avg latency: ${{d.latency_ms}}ms`;
  tip.style.opacity="1"; tip.style.left=(e.pageX+12)+"px"; tip.style.top=(e.pageY-28)+"px";
}}).on("mousemove",e=>{{
  tip.style.left=(e.pageX+12)+"px"; tip.style.top=(e.pageY-28)+"px";
}}).on("mouseout",()=>{{tip.style.opacity="0";}});

sim.on("tick", () => {{
  link.attr("x1", d=>d.source.x).attr("y1",d=>d.source.y)
      .attr("x2", d=>d.target.x).attr("y2",d=>d.target.y);
  linkLabel.attr("x",d=>(d.source.x+d.target.x)/2).attr("y",d=>(d.source.y+d.target.y)/2);
  node.attr("transform", d=>`translate(${{d.x}},${{d.y}})`);
}});
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Mermaid renderer (simple flowchart)
# ---------------------------------------------------------------------------

def _render_mermaid(graph: dict) -> str:
    lines = ["flowchart LR"]
    for edge in graph["edges"]:
        src  = edge["source"].replace("-", "_").replace(".", "_")
        tgt  = edge["target"].replace("-", "_").replace(".", "_")
        task = edge["task"][:40].replace('"', "'")
        lat  = f" ({edge['latency_ms']}ms)" if edge["latency_ms"] > 0 else ""
        lines.append(f'  {src} -->|"{task}{lat}"| {tgt}')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def plot_communication_flow(
    events: list[dict],
    fmt: str = "html",
    title: str = "MAS Agent Communication Flow",
) -> str:
    """Render an agent communication flow diagram.

    Parameters
    ----------
    events:
        Raw or normalized event list from a MAS trace.
    fmt:
        ``"html"`` (default) — interactive dark HTML with D3 force layout.
        ``"mermaid"`` — Mermaid flowchart string.
    title:
        Diagram title (HTML only).
    """
    graph = _extract_communication_graph(events)
    if not graph["edges"] and not graph["agents"]:
        return f"(no communication events found in {len(events)} events)"

    fmt = fmt.lower()
    if fmt == "mermaid":
        return _render_mermaid(graph)
    if fmt == "html":
        return _HTML_TEMPLATE.format(
            title=title,
            data_json=json.dumps(graph, ensure_ascii=False),
        )
    raise ValueError(f"Unknown format {fmt!r}. Use: html, mermaid")


# ---------------------------------------------------------------------------
# Processor wrapper
# ---------------------------------------------------------------------------

@register
class CommunicationFlowPlotter(Processor):
    """Render an agent-to-agent communication flow diagram.

    Accepts any :class:`~mas.lab.artifacts.Trajectory` or
    :class:`~mas.lab.artifacts.AnnotatedTrajectory` artifact and returns a
    :class:`~mas.lab.artifacts.PlotFile`.

    KWargs
    ------
    fmt : str
        ``"html"`` (default) or ``"mermaid"``.
    title : str
        Diagram title.
    output : str | Path, optional
        Write the rendered content to this path.
    """

    name        = "communication-flow-plotter"
    input_kind  = "trajectory"
    output_kind = "plot_file"
    description = "Renders an agent-to-agent communication flow diagram"
    priority    = 2

    def process(self, artifact: Any, **kwargs: Any) -> PlotFile:  # type: ignore[override]
        # Load events
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
                f"CommunicationFlowPlotter expects Trajectory, list[dict] or path-like, "
                f"got {type(artifact).__name__!r}"
            )

        fmt   = str(kwargs.pop("fmt", kwargs.pop("format", "html"))).lower()
        title = str(kwargs.pop("title", "MAS Agent Communication Flow"))

        content = plot_communication_flow(events, fmt=fmt, title=title)

        ext = {"html": ".html", "mermaid": ".mmd"}.get(fmt, ".txt")
        out_path = kwargs.pop("output", None)
        if out_path:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")

        return PlotFile(
            data=content,
            format=fmt,
            path=out_path,
        )
