#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Context provenance plot — prompt inspector with provenance annotations.

Renders an interactive HTML view showing the **actual assembled prompt text**
for each LLM call, with each context part colour-coded by source category
and annotated with provenance metadata on hover.

Data source
-----------
Reads ``context_part_contributed`` events from *events.jsonl* — one-shot
events emitted by :class:`ContextAssemblerPlugin` during ``on_pre_llm_call``.
Events must include a ``content`` field with the part text (runtime ≥ v0.14).

Design
------
* Each LLM call is a collapsible panel showing the full assembled prompt
* Each context part is a highlighted section coloured by source category:
  - SYSTEM (intent, role, instructions) — blue
  - SKILL (injected skill content) — green
  - MEMORY (semantic/episodic memory) — purple
  - TOOL (tool results, tool_call mechanism) — orange
  - RAG (retrieval-augmented content) — pink
* Hover tooltip shows provenance triplets and mechanism details
* Evicted parts shown with dashed border and reduced opacity
* Summary statistics at the bottom
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Union


__all__ = ["plot_context_provenance"]


# ── Source category palette ───────────────────────────────────────────────

_CATEGORIES: dict[str, dict[str, str]] = {
    "SYSTEM":  {"color": "#3b82f6", "bg": "rgba(59,130,246,.12)",  "label": "System Prompt"},
    "SKILL":   {"color": "#22c55e", "bg": "rgba(34,197,94,.12)",   "label": "Skill"},
    "MEMORY":  {"color": "#a855f7", "bg": "rgba(168,85,247,.12)",  "label": "Memory"},
    "TOOL":    {"color": "#f97316", "bg": "rgba(249,115,22,.12)",  "label": "Tool Result"},
    "RAG":     {"color": "#ec4899", "bg": "rgba(236,72,153,.12)",  "label": "RAG"},
    "CONTEXT": {"color": "#64748b", "bg": "rgba(100,116,139,.08)", "label": "Context"},
}

CAUSE_BADGE: dict[str, str] = {
    "deterministic": "⚙",
    "stochastic":    "🎲",
    "explicit":      "👤",
}

# Placement display order (system sections first, then user)
_PLACEMENT_ORDER = [
    "system_preamble", "system_header", "system_body", "system_skills",
    "system_suffix", "conversation_prepend", "user_prepend", "user_append",
]


def _source_category(source: str, mechanism: str = "inject") -> str:
    """Derive a human-readable category from a CPR source name."""
    sl = source.lower()
    if mechanism == "rag":
        return "RAG"
    if mechanism == "tool_call":
        return "TOOL"
    if sl.startswith("memory:") or sl.startswith("mem:"):
        return "MEMORY"
    if "skill" in sl or sl.startswith("facet:skill"):
        return "SKILL"
    if sl.startswith("context/role"):
        return "SYSTEM"
    if sl.startswith("context/intent"):
        return "SYSTEM"
    if sl.startswith("context/"):
        return "SYSTEM"
    if sl.startswith("tool:") or sl.startswith("tool_result"):
        return "TOOL"
    return "CONTEXT"


# ── Data extraction ──────────────────────────────────────────────────────

def _load_events(trace: Union[str, Path, list[dict]]) -> list[dict]:
    """Load events from JSONL file, path string, or event list."""
    if isinstance(trace, list):
        return trace
    path = Path(trace)
    events: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _extract_provenance_data(events: list[dict]) -> dict[str, Any]:
    """Group context_part_contributed events by LLM call.

    Returns
    -------
    dict with:
        calls : list[dict]  — ordered LLM call groups, each with:
            llm_call_id : str
            agent_id    : str
            timestamp   : float
            parts       : list[dict]  — context parts sorted by placement then priority
    """
    cpc_events = [e for e in events if e.get("kind") == "context_part_contributed"]
    if not cpc_events:
        return {"calls": []}

    by_call: dict[str, list[dict]] = defaultdict(list)
    for ev in cpc_events:
        key = ev.get("llm_call_id") or f"call@{ev['timestamp']:.3f}"
        by_call[key].append(ev)

    llm_events = [e for e in events if e.get("kind", "").startswith("llm_call")]
    llm_meta: dict[str, dict] = {}
    for le in llm_events:
        cid = le.get("call_id", "")
        if cid:
            llm_meta[cid] = le

    calls: list[dict] = []
    for call_id, parts in sorted(by_call.items(), key=lambda kv: kv[1][0]["timestamp"]):
        meta = llm_meta.get(call_id, {})
        # Sort by placement order, then by source name for stability
        def _sort_key(p: dict) -> tuple:
            placement = p.get("placement", "system_body")
            idx = _PLACEMENT_ORDER.index(placement) if placement in _PLACEMENT_ORDER else 99
            return (idx, p.get("source", ""))
        calls.append({
            "llm_call_id": call_id,
            "agent_id": parts[0].get("agent_id", "unknown"),
            "timestamp": parts[0]["timestamp"],
            "model": meta.get("model", ""),
            "parts": sorted(parts, key=_sort_key),
        })

    return {"calls": calls}


# ── HTML rendering ───────────────────────────────────────────────────────

def _escape(s: str) -> str:
    """HTML-escape a string."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _render_part_html(part: dict, part_idx: int) -> str:
    """Render a single context part as a prompt section with provenance."""
    source = part.get("source", "?")
    mechanism = part.get("access_mechanism", "inject")
    cause = part.get("cause", "?")
    cause_type = part.get("cause_type", "?")
    source_type = part.get("source_type", "?")
    tokens = part.get("token_estimate", 0)
    retained = part.get("retained", True)
    section = part.get("section_id", "")
    placement = part.get("placement", "system_body")
    content = part.get("content", "")
    badge = CAUSE_BADGE.get(cause_type, "")

    cat = _source_category(source, mechanism)
    cat_info = _CATEGORIES.get(cat, _CATEGORIES["CONTEXT"])
    color = cat_info["color"]
    bg = cat_info["bg"]
    cat_label = cat_info["label"]
    evicted_cls = " evicted" if not retained else ""

    # Build provenance tooltip data as JSON for JS
    prov_data = json.dumps({
        "source": source,
        "category": cat,
        "mechanism": mechanism,
        "cause": cause,
        "cause_type": cause_type,
        "source_type": source_type,
        "tokens": tokens,
        "retained": retained,
        "section": section,
        "placement": placement,
        "badge": badge,
        "eviction_reason": part.get("eviction_reason", ""),
    }, ensure_ascii=False)

    # Content display
    content_html = _escape(content) if content else "<em style='color:#64748b'>(no content captured in this trace)</em>"

    return (
        f'<div class="ctx-part{evicted_cls}" data-prov=\'{_escape(prov_data)}\''
        f' style="--bar-color:{color};--bg-color:{bg}">\n'
        f'  <div class="part-header">\n'
        f'    <span class="cat-label" style="background:{color}">{_escape(cat_label)}</span>\n'
        f'    <span class="part-source">{_escape(source)}</span>\n'
        f'    <span class="part-badges">\n'
        f'      <span class="badge mechanism" style="background:{color}">{_escape(mechanism)}</span>\n'
        f'      <span class="badge cause">{badge} {_escape(cause_type)}</span>\n'
        f'      <span class="badge tokens">{tokens} tok</span>\n'
        f'      <span class="badge placement">{_escape(placement)}</span>\n'
        + (f'      <span class="badge evicted-badge">evicted</span>\n' if not retained else '')
        + f'    </span>\n'
        f'  </div>\n'
        f'  <div class="part-content"><pre>{content_html}</pre></div>\n'
        f'</div>\n'
    )


def _render_html(data: dict[str, Any], title: str = "Context Provenance") -> str:
    """Render interactive HTML prompt inspector from provenance data."""
    calls = data.get("calls", [])
    if not calls:
        return "<html><body><p>No context_part_contributed events found.</p></body></html>"

    total_parts = 0
    total_tokens = 0
    mechanism_counts: dict[str, int] = defaultdict(int)
    cause_counts: dict[str, int] = defaultdict(int)

    calls_html_parts: list[str] = []
    for i, call in enumerate(calls):
        agent = _escape(call.get("agent_id", "?"))
        model = _escape(call.get("model", ""))
        cid = call.get("llm_call_id", "")
        short_id = cid[:16] if cid else f"call-{i+1}"
        call_tokens = sum(p.get("token_estimate", 0) for p in call["parts"])

        parts_html = []
        for j, part in enumerate(call["parts"]):
            parts_html.append(_render_part_html(part, j))
            total_parts += 1
            total_tokens += part.get("token_estimate", 0)
            mechanism_counts[part.get("access_mechanism", "inject")] += 1
            cause_counts[part.get("cause", "?")] += 1

        meta_parts = [f"agent: {agent}"]
        if model:
            meta_parts.append(f"model: {model}")
        meta_parts.append(f"{len(call['parts'])} parts · {call_tokens} tokens")

        calls_html_parts.append(
            f'<details class="call-panel" open>\n'
            f'  <summary class="call-header">\n'
            f'    <span class="call-title">LLM Call {i+1}</span>\n'
            f'    <span class="call-id">{_escape(short_id)}</span>\n'
            f'    <span class="call-meta">{_escape(" · ".join(meta_parts))}</span>\n'
            f'  </summary>\n'
            f'  <div class="call-body">\n'
            + "".join(parts_html)
            + f'  </div>\n'
            f'</details>\n'
        )

    calls_html = "\n".join(calls_html_parts)

    # Summary
    mech_items = " · ".join(f"{k}: {v}" for k, v in sorted(mechanism_counts.items()))
    cause_items = " · ".join(f"{k}: {v}" for k, v in sorted(cause_counts.items()))
    subtitle = f"{len(calls)} LLM call(s) · {total_parts} context parts · {total_tokens} tokens"

    summary_html = (
        '<div class="summary">\n'
        '  <h2>Summary</h2>\n'
        '  <div class="summary-grid">\n'
        f'    <div class="summary-card"><div class="label">LLM Calls</div>'
        f'<div class="value">{len(calls)}</div></div>\n'
        f'    <div class="summary-card"><div class="label">Context Parts</div>'
        f'<div class="value">{total_parts}</div></div>\n'
        f'    <div class="summary-card"><div class="label">Total Tokens</div>'
        f'<div class="value">{total_tokens}</div></div>\n'
        f'    <div class="summary-card"><div class="label">By Mechanism</div>'
        f'<div class="value" style="font-size:.78rem">{_escape(mech_items)}</div></div>\n'
        f'    <div class="summary-card"><div class="label">By Cause</div>'
        f'<div class="value" style="font-size:.78rem">{_escape(cause_items)}</div></div>\n'
        '  </div>\n'
        '</div>'
    )

    return _PROMPT_INSPECTOR_TEMPLATE.format(
        title=_escape(title),
        subtitle=_escape(subtitle),
        calls_html=calls_html,
        summary_html=summary_html,
    )


_PROMPT_INSPECTOR_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0 }}
body {{
  font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
  background: #0f172a; color: #e2e8f0; padding: 1.5rem; max-width: 1200px;
  margin: 0 auto;
}}
h1 {{ font-size: 1.3rem; font-weight: 700; color: #7dd3fc; margin-bottom: .5rem }}
.subtitle {{ font-size: .82rem; color: #94a3b8; margin-bottom: 1.5rem }}

/* Legend */
.legend {{
  display: flex; gap: 1.5rem; margin-bottom: 1.5rem; flex-wrap: wrap;
  font-size: .78rem; color: #94a3b8;
}}
.legend-item {{ display: flex; align-items: center; gap: .4rem }}
.legend-swatch {{
  width: 16px; height: 16px; border-radius: 3px; border: 1px solid #475569;
}}

/* Call panels */
.call-panel {{
  margin-bottom: 1.5rem; border: 1px solid #334155; border-radius: 8px;
  background: #1e293b; overflow: hidden;
}}
.call-header {{
  padding: .75rem 1rem; cursor: pointer; display: flex; align-items: center;
  gap: 1rem; font-size: .85rem; user-select: none;
}}
.call-header:hover {{ background: #253348 }}
.call-title {{ font-weight: 700; color: #7dd3fc; font-size: .95rem }}
.call-id {{ font-family: monospace; color: #64748b; font-size: .72rem }}
.call-meta {{ color: #94a3b8; font-size: .75rem; margin-left: auto }}
.call-body {{ padding: 0 }}

/* Context parts — prompt sections */
.ctx-part {{
  border-left: 4px solid var(--bar-color, #64748b);
  background: var(--bg-color, rgba(100,116,139,.05));
  margin: 0; padding: .6rem .75rem .6rem 1rem;
  position: relative; cursor: default;
  border-bottom: 1px solid #1a2332;
  transition: background .15s;
}}
.ctx-part:hover {{ background: rgba(255,255,255,.06) }}
.ctx-part.evicted {{
  opacity: .5; border-left-style: dashed;
  background: rgba(148,163,184,.04);
}}
.part-header {{
  display: flex; align-items: center; gap: .5rem; margin-bottom: .4rem;
  flex-wrap: wrap;
}}
.cat-label {{
  font-size: .65rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; padding: 2px 8px; border-radius: 3px;
  color: #fff;
}}
.part-source {{
  font-weight: 600; font-size: .8rem; color: #cbd5e1;
  font-family: ui-monospace, monospace;
}}
.part-badges {{ display: flex; gap: .35rem; flex-wrap: wrap; margin-left: auto }}
.badge {{
  font-size: .65rem; padding: 1px 6px; border-radius: 3px;
  color: rgba(255,255,255,.85); font-weight: 500;
}}
.badge.mechanism {{ /* colour set inline */ }}
.badge.cause {{ background: #334155; color: #94a3b8 }}
.badge.tokens {{ background: #1e293b; color: #64748b; border: 1px solid #334155 }}
.badge.placement {{ background: #1e293b; color: #475569; border: 1px solid #334155; font-family: monospace }}
.badge.evicted-badge {{ background: #7f1d1d; color: #fca5a5 }}

.part-content {{
  font-size: .78rem; line-height: 1.55; color: #cbd5e1;
}}
.part-content pre {{
  white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, monospace;
  margin: 0; max-height: 400px; overflow-y: auto; font-size: .75rem;
  padding: .4rem .5rem; background: rgba(0,0,0,.2); border-radius: 4px;
}}

/* Tooltip */
#tooltip {{
  position: fixed; display: none; max-width: 450px;
  background: #0f172a; color: #f1f5f9; border: 1px solid #475569;
  border-radius: 8px; padding: .75rem 1rem; font-size: .78rem;
  line-height: 1.6; box-shadow: 0 12px 32px rgba(0,0,0,.7);
  z-index: 9999; pointer-events: none;
}}
.tt-header {{ font-weight: 700; color: #7dd3fc; margin-bottom: .4rem; font-size: .85rem }}
.tt-cat {{ display: inline-block; font-size: .65rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; padding: 2px 8px; border-radius: 3px; color: #fff; margin-right: .4rem }}
.tt-sep {{ border: none; border-top: 1px solid #334155; margin: .4rem 0 }}
.tt-row {{ display: flex; gap: .5rem; margin-bottom: .15rem }}
.tt-label {{ color: #64748b; min-width: 110px; font-size: .72rem }}
.tt-value {{ color: #e2e8f0 }}
.triplet {{ color: #a5b4fc; font-family: monospace; font-size: .72rem; margin-top: .1rem }}

/* Summary */
.summary {{
  margin-top: 1.5rem; padding: 1rem; background: #1e293b;
  border-radius: 8px; border: 1px solid #334155;
}}
.summary h2 {{ font-size: .9rem; color: #7dd3fc; margin-bottom: .5rem }}
.summary-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: .5rem; font-size: .78rem;
}}
.summary-card {{
  background: #0f172a; border: 1px solid #334155; border-radius: 4px;
  padding: .5rem .75rem;
}}
.summary-card .label {{ color: #94a3b8; font-size: .72rem }}
.summary-card .value {{ color: #e2e8f0; font-size: 1rem; font-weight: 600 }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="subtitle">{subtitle}</p>

<div class="legend">
  <div class="legend-item"><div class="legend-swatch" style="background:#3b82f6"></div> System Prompt</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#22c55e"></div> Skill</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#a855f7"></div> Memory</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#f97316"></div> Tool Result</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#ec4899"></div> RAG</div>
  <div class="legend-item"><div class="legend-swatch" style="background:#334155; border:1.5px dashed #94a3b8; opacity:.5"></div> Evicted</div>
</div>

{calls_html}

{summary_html}

<div id="tooltip"></div>

<script>
const tooltip = document.getElementById('tooltip');
const CAT_COLORS = {{"SYSTEM":"#3b82f6","SKILL":"#22c55e","MEMORY":"#a855f7","TOOL":"#f97316","RAG":"#ec4899","CONTEXT":"#64748b"}};
const CAUSE_BADGE = {{"deterministic": "⚙", "stochastic": "🎲", "explicit": "👤"}};

function escH(s) {{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }}

document.querySelectorAll('.ctx-part').forEach(el => {{
  const raw = el.dataset.prov;
  if (!raw) return;
  let p;
  try {{ p = JSON.parse(raw.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"')) }} catch {{ return }}

  el.addEventListener('mouseenter', () => {{
    const badge = p.badge || '';
    const catColor = CAT_COLORS[p.category] || '#64748b';
    let html = `<span class="tt-cat" style="background:${{catColor}}">${{escH(p.category)}}</span>`;
    html += `<span class="tt-header">${{escH(p.source)}}</span><hr class="tt-sep">`;
    html += `<div class="tt-row"><span class="tt-label">mechanism</span><span class="tt-value">${{escH(p.mechanism)}}</span></div>`;
    html += `<div class="tt-row"><span class="tt-label">cause</span><span class="tt-value">${{badge}} ${{escH(p.cause)}} (${{escH(p.cause_type)}})</span></div>`;
    html += `<div class="tt-row"><span class="tt-label">source type</span><span class="tt-value">${{escH(p.source_type)}}</span></div>`;
    html += `<div class="tt-row"><span class="tt-label">placement</span><span class="tt-value">${{escH(p.placement)}}</span></div>`;
    html += `<div class="tt-row"><span class="tt-label">tokens</span><span class="tt-value">${{p.tokens}}</span></div>`;
    html += `<div class="tt-row"><span class="tt-label">retained</span><span class="tt-value">${{p.retained ? '✅' : '❌ evicted'}}</span></div>`;
    if (p.section) html += `<div class="tt-row"><span class="tt-label">section</span><span class="tt-value">${{escH(p.section)}}</span></div>`;
    html += '<hr class="tt-sep"><div style="color:#64748b;font-size:.7rem;margin-bottom:.2rem">Provenance triplets:</div>';
    const s = escH(p.source);
    html += `<div class="triplet">(${{s}}, accessMechanism, ${{escH(p.mechanism)}})</div>`;
    html += `<div class="triplet">(${{s}}, cause, ${{escH(p.cause)}})</div>`;
    html += `<div class="triplet">(${{s}}, causeType, ${{escH(p.cause_type)}})</div>`;
    html += `<div class="triplet">(${{s}}, sourceType, ${{escH(p.source_type)}})</div>`;
    html += `<div class="triplet">(${{s}}, tokenEstimate, ${{p.tokens}})</div>`;
    if (!p.retained && p.eviction_reason)
      html += `<div class="triplet">(${{s}}, evictionReason, ${{escH(p.eviction_reason)}})</div>`;
    tooltip.innerHTML = html;
    tooltip.style.display = 'block';
  }});
  el.addEventListener('mousemove', e => {{
    const pad = 14;
    let x = e.clientX + pad, y = e.clientY + pad;
    const r = tooltip.getBoundingClientRect();
    if (x + r.width > window.innerWidth) x = e.clientX - r.width - pad;
    if (y + r.height > window.innerHeight) y = e.clientY - r.height - pad;
    tooltip.style.left = x + 'px'; tooltip.style.top = y + 'px';
  }});
  el.addEventListener('mouseleave', () => {{ tooltip.style.display = 'none' }});
}});
</script>
</body>
</html>
"""


# ── Public API ───────────────────────────────────────────────────────────

def plot_context_provenance(
    trace: Union[str, Path, list[dict]],
    *,
    title: str = "Context Provenance",
    output: Union[str, Path, None] = None,
) -> str:
    """Render context provenance prompt inspector from events.

    Parameters
    ----------
    trace
        Event list, path to events.jsonl, or JSONL string.
    title
        Chart title.
    output
        If given, write HTML to this path and return the path as string.

    Returns
    -------
    str
        HTML string (or output path if *output* is provided).
    """
    events = _load_events(trace)
    data = _extract_provenance_data(events)
    html = _render_html(data, title=title)

    if output is not None:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return str(out)

    return html
