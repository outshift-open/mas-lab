#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""HTML trajectory output."""

import json as _json
import textwrap

from mas.lab.plots.trajectory.extract import _short_task
from mas.lab.plots.trajectory.mermaid import _fmt_mermaid

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MAS Trajectory</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    body {{ font-family: sans-serif; padding: 2rem; background: #f9fafb; }}
    .mermaid {{ background: white; padding: 1rem; border-radius: 8px;
                box-shadow: 0 1px 4px rgba(0,0,0,.12); }}
    h1 {{ color: #1e293b; font-size: 1.4rem; }}
    p.meta {{ color: #64748b; font-size: .85rem; }}
    .has-tip {{ cursor: help; text-decoration: underline dotted #94a3b8; }}
    .has-hl  {{ cursor: pointer; }}
    .has-agent-hl {{ cursor: default; }}
  </style>
</head>
<body>
  <h1>MAS Agent Trajectory</h1>
  <p class="meta">{n_delegations} delegation(s) · {n_agents} agent(s)</p>
  <div class="mermaid">
{diagram}
  </div>
  <script>
    const _TIPS      = {tooltip_json};
    const _HLABELS   = new Set({highlights_json});
    const _HAGENTS   = new Set({hagents_json});
    mermaid.initialize({{startOnLoad: false, theme: 'default'}});
    document.addEventListener('DOMContentLoaded', () => {{
      mermaid.run({{querySelector: '.mermaid'}}).then(() => {{
        document.querySelectorAll('.mermaid svg text, .mermaid svg tspan').forEach(el => {{
          const key = el.textContent.trim();
          // ── tooltips ──
          if (_TIPS[key]) {{
            const t = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            t.textContent = _TIPS[key];
            el.parentElement.insertBefore(t, el.parentElement.firstChild);
            el.classList.add('has-tip');
          }}
          // ── highlights (amber recolor) ──
          if (_HLABELS.has(key)) {{
            el.style.fill = '#92400e';
            el.style.fontWeight = 'bold';
            el.classList.add('has-hl');
            try {{
              const bbox = el.getBBox();
              const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
              rect.setAttribute('x',      String(bbox.x - 3));
              rect.setAttribute('y',      String(bbox.y));
              rect.setAttribute('width',  String(bbox.width + 6));
              rect.setAttribute('height', String(bbox.height));
              rect.setAttribute('fill',   '#fef3c7');
              rect.setAttribute('rx',     '3');
              rect.setAttribute('stroke', '#f59e0b');
              rect.setAttribute('stroke-width', '1.5');
              el.parentNode.insertBefore(rect, el);
            }} catch (_) {{}}
            // recolor any arrow line in the same message group
            const g = el.closest('g');
            if (g) {{
              g.querySelectorAll('line, path[d]').forEach(arrow => {{
                if (!arrow.getAttribute('d')?.startsWith('M0')) {{
                  arrow.style.stroke = '#d97706';
                  arrow.style.strokeWidth = '2.5';
                }}
              }});
            }}
          }}
          // ── agent node highlights (participant/actor boxes) ──
          if (_HAGENTS.has(key)) {{
            el.style.fill = '#d97706';
            el.style.fontWeight = 'bold';
            el.classList.add('has-agent-hl');
            const g2 = el.closest('g');
            if (g2) {{
              g2.querySelectorAll('rect, polygon').forEach(s => {{
                s.style.fill   = '#451a03';
                s.style.stroke = '#d97706';
                s.style.strokeWidth = '2';
              }});
            }}
          }}
        }});
      }});
    }});
  </script>
</body>
</html>
"""


def _build_tooltip_map(delegations: list[dict], include_prompts: bool) -> dict[str, str]:
    """Map every short label used in the Mermaid diagram to its full text."""
    tips: dict[str, str] = {}
    for i, d in enumerate(delegations, 1):
        cid_short = d["correlation_id"][:8] if d["correlation_id"] else f"#{i}"

        if d.get("fwd_only"):
            if include_prompts and d["task"]:
                short = _short_task(d["task"])
                full = d["task"]
                if short != full:
                    tips[short] = full
            continue

        if d.get("ret_only"):
            if include_prompts and d.get("output"):
                short = _short_task(d["output"], max_chars=80)
                full = d["output"]
                if short != full:
                    tips[short] = full
            continue

        # regular delegation — forward label
        if include_prompts and d["task"]:
            short_task = _short_task(d["task"])
            fwd_label = f"[{cid_short}] {short_task}"
            tips[fwd_label] = d["task"]
            tips[short_task] = d["task"]

        # return label
        if include_prompts and d.get("output"):
            short_out = _short_task(d["output"], max_chars=70)
            if short_out != d["output"]:
                tips[short_out] = d["output"]

    return tips


def _build_highlight_labels(
    delegations: list[dict], include_prompts: bool
) -> list[str]:
    """Return the short labels of highlighted delegations (for JS Set)."""
    labels: list[str] = []
    for i, d in enumerate(delegations, 1):
        if not d.get("highlighted"):
            continue
        if d.get("fwd_only") or d.get("ret_only"):
            continue
        cid_short = d["correlation_id"][:8] if d["correlation_id"] else f"#{i}"
        if include_prompts and d["task"]:
            short_task = _short_task(d["task"])
            labels.append(f"[{cid_short}] {short_task}")
            labels.append(short_task)
        else:
            labels.append(f"delegate [{cid_short}]")
        if include_prompts and d.get("output"):
            labels.append(_short_task(d["output"], max_chars=70))
    return labels


def _fmt_html(
    delegations: list[dict],
    agents: list[str],
    include_prompts: bool,
    highlight_agents: list[str] | None = None,
) -> str:
    """Render a self-contained HTML page with hover tooltips and highlights."""
    import json as _json
    diagram = _fmt_mermaid(delegations, agents, include_prompts)
    indented = textwrap.indent(diagram, "    ")
    tooltip_map = _build_tooltip_map(delegations, include_prompts)
    highlight_labels = _build_highlight_labels(delegations, include_prompts)
    return _HTML_TEMPLATE.format(
        n_delegations=len(delegations),
        n_agents=len(agents),
        diagram=indented,
        tooltip_json=_json.dumps(tooltip_map, ensure_ascii=False),
        highlights_json=_json.dumps(highlight_labels, ensure_ascii=False),
        hagents_json=_json.dumps(list(highlight_agents) if highlight_agents else [], ensure_ascii=False),
    )
