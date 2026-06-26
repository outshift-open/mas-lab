#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""SVG sequence diagram renderers."""

from mas.lab.plots.trajectory.extract import _short_task
from mas.lab.plots.trajectory.mermaid import _fmt_mermaid

# ---------------------------------------------------------------------------
# SVG sequence diagram renderer
# ---------------------------------------------------------------------------

_SVG_COLORS = {
    "bg": "#f8fafc",
    "lifeline": "#94a3b8",
    "box_fill": "#1e40af",
    "box_stroke": "#1e3a8a",
    "box_text": "#ffffff",
    "arrow_fwd": "#0f172a",
    "arrow_ret": "#64748b",
    "label_bg": "#eff6ff",
    "label_stroke": "#bfdbfe",
    "label_text": "#1e293b",
    "success": "#16a34a",
    "failure": "#dc2626",
    "title": "#0f172a",
}


def _svg_escape(text: str) -> str:
    return (text.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace('"', "&quot;"))


def _wrap_label(text: str, max_chars: int = 38) -> list[str]:
    """Wrap text into lines of at most max_chars characters."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).lstrip()
    if current:
        lines.append(current)
    return lines or [""]


def _fmt_svg_mermaid(delegations: list[dict], agents: list[str], include_prompts: bool) -> str:
    """Render a Mermaid sequence diagram to SVG via headless Chromium (playwright).

    Falls back to :func:`_fmt_svg_native` on any failure.
    """
    import os, tempfile

    diagram = _fmt_mermaid(delegations, agents, include_prompts)
    html = (
        "<!DOCTYPE html><html><head>"
        '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>'
        "<style>body{margin:0;padding:16px;background:white;}"
        ".mermaid{display:inline-block;}</style></head><body>"
        f'<div class="mermaid">\n{diagram}\n</div>'
        "<script>mermaid.initialize({startOnLoad:true,theme:'default'});</script>"
        "</body></html>"
    )
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8")
    try:
        tmp.write(html)
        tmp.close()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{tmp.name}")
            page.wait_for_selector(".mermaid svg", timeout=15_000)
            svg_content: str = page.evaluate(
                "() => document.querySelector('.mermaid svg').outerHTML"
            )
            browser.close()
        return svg_content
    except Exception:
        return _fmt_svg_native(delegations, agents, include_prompts)
    finally:
        os.unlink(tmp.name)


def _fmt_svg_native(
    delegations: list[dict],
    agents: list[str],
    include_prompts: bool,
    highlight_agents: list[str] | None = None,
) -> str:
    """Render a standalone hand-drawn SVG sequence diagram (no external dependencies)."""
    # Layout constants
    PAD_LEFT = 60
    AGENT_W = 110
    AGENT_H = 32
    AGENT_GAP = 50          # gap between agent boxes (column spacing = AGENT_W + AGENT_GAP)
    COL_STEP = AGENT_W + AGENT_GAP
    ROW_START = 80          # y of first delegation row (below agent boxes)
    ROW_H = 95              # vertical space per arrow slot
    LABEL_H_LINE = 14       # height per label text line
    LABEL_PAD = 6
    LIFELINE_EXTRA = 40     # extra lifeline below last row

    n_agents = len(agents)
    agent_idx = {a: i for i, a in enumerate(agents)}

    total_width = PAD_LEFT * 2 + n_agents * COL_STEP - AGENT_GAP
    total_height = 600  # placeholder — patched after arrow layout

    parts: list[str] = []

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_width}" height="{total_height}" '
        f'viewBox="0 0 {total_width} {total_height}" '
        f'font-family="ui-monospace,SFMono-Regular,Consolas,monospace" '
        f'font-size="11">'
    )
    # background
    parts.append(
        f'<rect width="{total_width}" height="{total_height}" '
        f'fill="{_SVG_COLORS["bg"]}"/>'
    )
    # title
    parts.append(
        f'<text x="{total_width // 2}" y="20" text-anchor="middle" '
        f'font-size="13" font-weight="bold" fill="{_SVG_COLORS["title"]}">'
        f'MAS Agent Trajectory</text>'
    )

    # ── agent boxes ──
    box_y = 40
    center_x = [PAD_LEFT + i * COL_STEP + AGENT_W // 2 for i in range(n_agents)]

    _HL_BOX        = "#d97706"
    _HL_BOX_STROKE = "#b45309"
    for i, agent in enumerate(agents):
        cx = center_x[i]
        bx = cx - AGENT_W // 2
        hl_a = bool(highlight_agents and agent in highlight_agents)
        abox_fill   = _HL_BOX        if hl_a else _SVG_COLORS["box_fill"]
        abox_stroke = _HL_BOX_STROKE if hl_a else _SVG_COLORS["box_stroke"]
        parts.append(
            f'<rect x="{bx}" y="{box_y}" width="{AGENT_W}" height="{AGENT_H}" '
            f'rx="6" fill="{abox_fill}" stroke="{abox_stroke}" stroke-width="1.5"/>'
        )
        a_label = ("⚠ " + agent) if hl_a else agent
        parts.append(
            f'<text x="{cx}" y="{box_y + AGENT_H // 2 + 5}" text-anchor="middle" '
            f'font-weight="bold" fill="{_SVG_COLORS["box_text"]}">{_svg_escape(a_label)}</text>'
        )

    # ── lifelines ──
    lifeline_top = box_y + AGENT_H
    lifeline_bot = total_height - LIFELINE_EXTRA + 10
    for i in range(n_agents):
        cx = center_x[i]
        parts.append(
            f'<line x1="{cx}" y1="{lifeline_top}" x2="{cx}" y2="{lifeline_bot}" '
            f'stroke="{_SVG_COLORS["lifeline"]}" stroke-width="1" stroke-dasharray="4,3"/>'
        )

    # ── defs: arrowheads ──
    parts.append(
        '<defs>'
        f'<marker id="arr-fwd" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">'
        f'<path d="M0,0 L8,3 L0,6 Z" fill="{_SVG_COLORS["arrow_fwd"]}"/></marker>'
        f'<marker id="arr-ret" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">'
        f'<path d="M0,0 L8,3 L0,6 Z" fill="{_SVG_COLORS["arrow_ret"]}"/></marker>'
        '</defs>'
    )

    # ── expand delegations into individual timestamped arrows, sort by ts ──
    arrows: list[dict] = []
    for idx, d in enumerate(delegations):
        arrows.append({**d, "_kind": "fwd", "_ts": d["ts_start"], "_orig_idx": idx})
        arrows.append({**d, "_kind": "ret", "_ts": d["ts_end"],   "_orig_idx": idx})
    arrows.sort(key=lambda a: (a["_ts"], 0 if a["_kind"] == "fwd" else 1))

    def _arrow_extra(a: dict) -> int:
        if a["_kind"] == "fwd":
            fwd_lines = len(_wrap_label(_short_task(a["task"]))) if (include_prompts and a["task"]) else 1
            return (fwd_lines - 1) * LABEL_H_LINE
        else:
            ret_lines = len(_wrap_label(a["output"][:160], max_chars=40)) if (include_prompts and a.get("output")) else 1
            return (ret_lines - 1) * LABEL_H_LINE

    _arrow_extras = [_arrow_extra(a) for a in arrows]
    total_height = (ROW_START + AGENT_H + box_y
                    + sum(ROW_H // 2 + e for e in _arrow_extras)
                    + LIFELINE_EXTRA + 20)
    parts[0] = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_width}" height="{total_height}" '
        f'viewBox="0 0 {total_width} {total_height}" '
        f'font-family="ui-monospace,SFMono-Regular,Consolas,monospace" '
        f'font-size="11">'
    )
    parts[1] = (
        f'<rect width="{total_width}" height="{total_height}" '
        f'fill="{_SVG_COLORS["bg"]}"/>'
    )
    for i, p in enumerate(parts):
        if 'stroke-dasharray="4,3"' in p and 'line' in p:
            parts[i] = p.replace(f'y2="{lifeline_bot}"',
                                  f'y2="{total_height - LIFELINE_EXTRA + 10}"')

    _HL = {
        "arrow": "#d97706",
        "label_bg": "#fef3c7",
        "label_stroke": "#f59e0b",
        "label_text": "#92400e",
    }

    y_cursor = ROW_START + AGENT_H + box_y
    ARROW_H = ROW_H // 2

    for arrow in arrows:
        src_i = agent_idx.get(arrow["source"], 0)
        tgt_i = agent_idx.get(arrow["target"], 0)
        src_x = center_x[src_i]
        tgt_x = center_x[tgt_i]
        extra = _arrow_extra(arrow)
        slot_h = ARROW_H + extra
        arrow_y = y_cursor + slot_h // 2
        going_right = tgt_i >= src_i
        hl = arrow.get("highlighted", False)
        cid = arrow["correlation_id"][:8] if arrow["correlation_id"] else "#?"

        if arrow["_kind"] == "fwd":
            fwd_stroke = _HL["arrow"] if hl else _SVG_COLORS["arrow_fwd"]
            fwd_sw = "2.5" if hl else "1.5"
            ax1 = src_x + (5 if going_right else -5)
            ax2 = tgt_x - (8 if going_right else -8)
            parts.append(
                f'<line x1="{ax1}" y1="{arrow_y}" x2="{ax2}" y2="{arrow_y}" '
                f'stroke="{fwd_stroke}" stroke-width="{fwd_sw}" '
                f'marker-end="url(#arr-fwd)"/>'
            )
            if hl:
                bx = min(ax1, ax2) - 16
                parts.append(
                    f'<text x="{bx}" y="{arrow_y + 4}" text-anchor="middle" '
                    f'font-size="13">⚠️</text>'
                )
            if include_prompts and arrow["task"]:
                lines = _wrap_label(_short_task(arrow["task"]))
            else:
                lines = [f"[{cid}] delegate"]
            lbl_w = min(abs(tgt_x - src_x) - 16, 200)
            lbl_h = LABEL_PAD * 2 + len(lines) * LABEL_H_LINE
            lbl_cx = (src_x + tgt_x) // 2
            lbl_x = lbl_cx - lbl_w // 2
            lbl_y = arrow_y - lbl_h - 2
            lbl_bg     = _HL["label_bg"]     if hl else _SVG_COLORS["label_bg"]
            lbl_stroke_c = _HL["label_stroke"] if hl else _SVG_COLORS["label_stroke"]
            lbl_text_c   = _HL["label_text"]   if hl else _SVG_COLORS["label_text"]
            lbl_sw2 = "1.5" if hl else "1"
            parts.append(
                f'<rect x="{lbl_x}" y="{lbl_y}" width="{lbl_w}" height="{lbl_h}" '
                f'rx="3" fill="{lbl_bg}" stroke="{lbl_stroke_c}" stroke-width="{lbl_sw2}"/>'
            )
            for li, line in enumerate(lines):
                ty = lbl_y + LABEL_PAD + (li + 1) * LABEL_H_LINE - 2
                parts.append(
                    f'<text x="{lbl_cx}" y="{ty}" text-anchor="middle" '
                    f'fill="{lbl_text_c}">{_svg_escape(line)}</text>'
                )
        else:  # ret
            status_color = (_SVG_COLORS["success"] if arrow["status"] == "success"
                            else _SVG_COLORS["failure"])
            ax1 = tgt_x - (5 if going_right else -5)
            ax2 = src_x + (8 if going_right else -8)
            parts.append(
                f'<line x1="{ax1}" y1="{arrow_y}" x2="{ax2}" y2="{arrow_y}" '
                f'stroke="{status_color}" stroke-width="1.2" stroke-dasharray="5,3" '
                f'marker-end="url(#arr-ret)"/>'
            )
            if include_prompts and arrow.get("output"):
                ret_lines = _wrap_label(arrow["output"][:160], max_chars=40)
            else:
                ret_lines = [arrow["status"]]
            lbl_w = min(abs(tgt_x - src_x) - 16, 200)
            lbl_h = LABEL_PAD * 2 + len(ret_lines) * LABEL_H_LINE
            lbl_cx = (src_x + tgt_x) // 2
            lbl_x = lbl_cx - lbl_w // 2
            lbl_y = arrow_y + 2
            parts.append(
                f'<rect x="{lbl_x}" y="{lbl_y}" width="{lbl_w}" height="{lbl_h}" '
                f'rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1"/>'
            )
            for li, rline in enumerate(ret_lines):
                ty = lbl_y + LABEL_PAD + (li + 1) * LABEL_H_LINE - 2
                parts.append(
                    f'<text x="{lbl_cx}" y="{ty}" text-anchor="middle" '
                    f'font-size="10" fill="{status_color}">{_svg_escape(rline)}</text>'
                )

        y_cursor += slot_h

    parts.append("</svg>")
    return "\n".join(parts)

