#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""SVG renderer for multilevel trajectory diagrams."""

from collections import defaultdict

from mas.lab.plots.multilevel_trajectory.constants import (
    _INSTANT_ICON,
    _INSTANT_ICON_DEFAULT,
)
from mas.lab.plots.multilevel_trajectory.layout import _compute_x_positions
from mas.lab.plots.multilevel_trajectory.models import LaneDef, StateNode, TransNode
from mas.lab.plots.palette import PALETTE

def _esc(t: str) -> str:
    """Escape for SVG text/title content."""
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _ea(t: str) -> str:
    """Escape for use inside a double-quoted HTML/SVG attribute value."""
    return (
        t.replace("&", "&amp;").replace("<", "&lt;")
         .replace(">", "&gt;").replace('"', "&quot;")
         .replace("\n", "&#10;").replace("\r", "")
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BG        = "#0f172a"
_LANE_BG   = "#1e293b"
_LANE_ALT  = "#172032"
_SEP       = "#334155"
_LABEL_C   = "#94a3b8"
_TITLE_C   = "#f1f5f9"
_STATE_F      = "#ffffff"
_STATE_S      = "#475569"
_STATE_T      = "#1e293b"
_BADGE_F      = "#f87171"
_CONN_C       = "#475569"
_ARROW_C      = "#64748b"
_USER_ACTOR_C    = "#eab308"   # yellow-500: user actor (distinct from LLM orange #ea580c)
_USER_ACTOR_OFFSET = 60          # px from boundary state centre to user box centre

_LABEL_W  = 108
_PAD_L    = 80   # must fit user box left edge: UA_OFFSET + STATE_W/2 + margin past label col
_PAD_R    = 80   # must fit user box right edge: UA_OFFSET + STATE_W/2 + margin
_TITLE_H  = 48
_LEGEND_H = 34
_LANE_H   = 68
_LANE_MID = 34
_PAD_BOT  = 20
_STATE_W    = 34
_STATE_H    = 26
_TRANS_H    = 26
_BADGE_R    = 10
_ARR_GAP    = 10
_MIN_TRANS_W = 80

_LEVEL_ACCENT: dict[str, str] = {
    "session": PALETTE["session"],
    "mas":     PALETTE["mas"],
    "agent":   PALETTE["agent"],
    "call":    PALETTE["processing"],
}


# ---------------------------------------------------------------------------
# SVG renderer
# ---------------------------------------------------------------------------

def _render_svg(
    state_reg: dict[float, StateNode],
    lanes: list[LaneDef],
    title: str,
    width_mode: str = "fixed",
    show_user_actors: bool = True,
) -> str:
    all_buckets = sorted(state_reg.keys())
    # Sub-states (e.g. S2a) have label_override and must NOT consume a numeric
    # slot — otherwise the next plain state (S3) would be numbered S4.
    _numbered_buckets = [b for b in all_buckets if not state_reg[b].label_override]
    _numbered_seq     = {b: i + 1 for i, b in enumerate(_numbered_buckets)}
    # state_num maps every bucket to its display number (sub-states keep the
    # parent number so positional lookups still work; the label_override takes
    # precedence when rendering).
    state_num: dict[float, int] = {
        b: _numbered_seq.get(b, _numbered_seq.get(
            max((nb for nb in _numbered_buckets if nb < b), default=_numbered_buckets[0])
            if _numbered_buckets else b, 1
        ))
        for b in all_buckets
    }
    if not all_buckets:
        return "<svg xmlns='http://www.w3.org/2000/svg'><text fill='white' y='20'>No data</text></svg>"

    # Build set of genuine instant-call column intervals (ToolCall/MemoryCall/RAGQuery,
    # not ProcessingCall which overlays its own state bucket).
    instant_pairs: frozenset[tuple[float, float]] = frozenset(
        (tr.start_ts, tr.end_ts)
        for lane in lanes
        for tr in lane.sequence
        if isinstance(tr, TransNode) and tr.is_instant and tr.call_type != "ProcessingCall"
    )

    xpos = _compute_x_positions(all_buckets, _LABEL_W, _PAD_L, min_col=150.0, width_mode=width_mode, instant_pairs=instant_pairs)

    total_w = max(xpos.values()) + _PAD_R
    total_h = _TITLE_H + _LEGEND_H + len(lanes) * _LANE_H + _PAD_BOT

    def cx(ts: float) -> float:
        snapped = min(all_buckets, key=lambda b: abs(b - ts))
        return xpos.get(snapped, _LABEL_W + _PAD_L)

    def lane_y(li: int) -> float:
        return float(_TITLE_H + _LEGEND_H + li * _LANE_H)

    def lane_cy(li: int) -> float:
        return lane_y(li) + _LANE_MID

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg"',
        f' width="{total_w:.0f}" height="{total_h:.0f}"',
        f' viewBox="0 0 {total_w:.0f} {total_h:.0f}"',
        f' font-family="ui-monospace,SFMono-Regular,Consolas,monospace"',
        f' font-size="11">',
        f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="{_BG}"/>',
        '<defs>',
        f'<marker id="arr" markerWidth="6" markerHeight="5" refX="5" refY="2.5" orient="auto">',
        f'<path d="M0,0 L6,2.5 L0,5 Z" fill="{_ARROW_C}"/></marker>',
        '</defs>',
    ]

    # Title
    parts.append(
        f'<text x="{_LABEL_W + _PAD_L:.0f}" y="{_TITLE_H - 12}"',
    )
    parts.append(
        f' font-size="16" font-weight="bold" fill="{_TITLE_C}">{_esc(title)}</text>',
    )

    # Legend
    leg_top = _TITLE_H
    parts.append(f'<rect x="0" y="{leg_top}" width="{total_w:.0f}" height="{_LEGEND_H}" fill="{_LANE_ALT}"/>')
    parts.append(f'<text x="8" y="{leg_top + 22}" font-size="10" font-weight="bold" fill="{_LABEL_C}">LEVEL</text>')
    swatches = [
        ("session",    PALETTE["session"]),
        ("mas",        PALETTE["mas"]),
        ("agent",      PALETTE["agent"]),
        ("llm",        PALETTE["llm"]),
        ("tool",       PALETTE["tool"]),
        ("memory",     PALETTE["memory"]),
        ("rag",        PALETTE["rag"]),
        ("processing", PALETTE["processing"]),
        ("user",       _USER_ACTOR_C),
    ]
    sx = float(_LABEL_W + 16)
    for slabel, scol in swatches:
        parts.append(f'<rect x="{sx:.0f}" y="{leg_top + 11}" width="12" height="12" fill="{scol}" rx="2"/>')
        parts.append(f'<text x="{sx + 16:.0f}" y="{leg_top + 22}" font-size="10" fill="{_LABEL_C}">{slabel}</text>')
        sx += 16 + len(slabel) * 6.8 + 12

    # Lane backgrounds + labels
    for li, lane in enumerate(lanes):
        lt  = lane_y(li)
        bg  = _LANE_BG if li % 2 == 0 else _LANE_ALT
        acc = _LEVEL_ACCENT.get(lane.level, _SEP)
        parts += [
            f'<rect x="0" y="{lt:.0f}" width="{total_w:.0f}" height="{_LANE_H}" fill="{bg}"/>',
            f'<rect x="0" y="{lt:.0f}" width="4" height="{_LANE_H}" fill="{acc}"/>',
            f'<line x1="0" y1="{lt:.0f}" x2="{total_w:.0f}" y2="{lt:.0f}" stroke="{_SEP}" stroke-width="0.5"/>',
            f'<text x="{_LABEL_W - 8}" y="{lt + _LANE_MID + 4:.0f}" text-anchor="end" font-size="11" fill="{_LABEL_C}">{_esc(lane.label)}</text>',
        ]

    bot = lane_y(len(lanes))
    parts.append(f'<line x1="0" y1="{bot:.0f}" x2="{total_w:.0f}" y2="{bot:.0f}" stroke="{_SEP}" stroke-width="0.5"/>')

    # ── Phase 1: lifelines + transitions (all lanes, drawn first) ───────────
    for li, lane in enumerate(lanes):
        cy  = lane_cy(li)
        seq = lane.sequence
        if not seq:
            continue

        # Lifeline
        state_xs = [cx(el.ts) for el in seq if isinstance(el, StateNode)]
        if len(state_xs) >= 2:
            parts.append(
                f'<line x1="{state_xs[0]:.1f}" y1="{cy:.1f}"'
                f' x2="{state_xs[-1]:.1f}" y2="{cy:.1f}"'
                f' stroke="{_SEP}" stroke-width="0.8" stroke-dasharray="3,4" opacity="0.4"/>'
            )

        # Transitions (instant calls deferred to Phase 4)
        for el in seq:
            if not isinstance(el, TransNode):
                continue
            if el.is_instant:
                continue

            # If the lane has an instant-call icon at start_ts, push the bar
            # right to start after the icon (avoids overlap).
            _has_instant_here = any(
                isinstance(e, TransNode) and e.is_instant
                and abs(e.start_ts - el.start_ts) <= 1e-6
                for e in seq
            )
            if _has_instant_here:
                x_left = cx(el.start_ts) + _STATE_W // 2 + 4 + _STATE_W + _ARR_GAP
            else:
                x_left = cx(el.start_ts) + _STATE_W // 2 + _ARR_GAP
            x_right = cx(el.end_ts)   - _STATE_W // 2 - _ARR_GAP
            x_right = max(x_right, x_left + _MIN_TRANS_W)
            tw    = x_right - x_left
            mid   = (x_left + x_right) / 2
            ty    = cy - _TRANS_H // 2
            color = el.color

            # Transition tooltip: input → output
            raw_content = (
                (el.hover_in or "(no input)")
                + "\n\n→\n\n"
                + (el.hover_out or "(no output)")
            )
            content = _ea(raw_content[:1200])

            parts.append(
                f'<rect x="{x_left:.1f}" y="{ty:.1f}" width="{tw:.1f}" height="{_TRANS_H}"'
                f' rx="4" fill="{color}"'
                f' data-label="{_esc(el.label)}"'
                f' data-content="{content}"'
                f' style="cursor:pointer"/>'
            )
            max_chars = max(3, int(tw / 7))
            parts.append(
                f'<text x="{mid:.1f}" y="{cy + 4:.1f}"'
                f' text-anchor="middle" font-size="10" font-weight="bold"'
                f' fill="#ffffff" pointer-events="none">{_esc(el.label[:max_chars])}</text>'
            )
            bx = min(x_left + tw * 0.82, x_right - _BADGE_R - 1)
            by = ty + _BADGE_R + 1
            parts += [
                f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{_BADGE_R}" fill="{_BADGE_F}"/>',
                f'<text x="{bx:.1f}" y="{by + 4:.1f}" text-anchor="middle"'
                f' font-size="9" font-weight="bold" fill="#ffffff">{el.seq}</text>',
            ]
            # Skip left arrow when an instant-call icon fills that space.
            if not _has_instant_here:
                arr_x0 = cx(el.start_ts) + _STATE_W // 2
                if x_left - arr_x0 > 2:
                    parts.append(
                        f'<line x1="{arr_x0:.1f}" y1="{cy:.1f}" x2="{x_left:.1f}" y2="{cy:.1f}"'
                        f' stroke="{_ARROW_C}" stroke-width="1.5" marker-end="url(#arr)"/>'
                    )
            arr_x2 = cx(el.end_ts) - _STATE_W // 2
            if arr_x2 - x_right > 2:
                parts.append(
                    f'<line x1="{x_right:.1f}" y1="{cy:.1f}" x2="{arr_x2:.1f}" y2="{cy:.1f}"'
                    f' stroke="{_ARROW_C}" stroke-width="1.5" marker-end="url(#arr)"/>'
                )

    # ── Phase 2: vertical shared-state connectors (between lane centers) ────
    # Drawn after transitions but before state boxes so they appear behind states.
    bucket_to_lane_indices: dict[float, list[int]] = defaultdict(list)
    for li, lane in enumerate(lanes):
        seen_b: set[float] = set()
        for el in lane.sequence:
            if isinstance(el, StateNode) and el.ts not in seen_b:
                bucket_to_lane_indices[el.ts].append(li)
                seen_b.add(el.ts)

    for ts, lane_indices in sorted(bucket_to_lane_indices.items()):
        unique = sorted(set(lane_indices))
        if len(unique) < 2:
            continue
        xc = cx(ts)
        # Draw segment between each consecutive pair of contributing lanes so
        # the line only appears in the gap (not through the state boxes).
        for a, b in zip(unique, unique[1:]):
            y1 = lane_cy(a) + _STATE_H // 2 + 2
            y2 = lane_cy(b) - _STATE_H // 2 - 2
            if y2 > y1:
                parts.append(
                    f'<line x1="{xc:.1f}" y1="{y1:.1f}" x2="{xc:.1f}" y2="{y2:.1f}"'
                    f' stroke="{_CONN_C}" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.85"/>'
                )

    def _svg_user_actor(scx: float, cy: float, is_entry: bool, hover: str) -> None:
        """Draw a box-shaped user node adjacent to the boundary state.

        Same size as a state box (SW×SH), filled with user colour, with a
        small person silhouette drawn in dark ink inside.  The direction
        (entry / exit) is implicit from position — no text label needed.
        """
        ux      = scx - _USER_ACTOR_OFFSET if is_entry else scx + _USER_ACTOR_OFFSET
        caption = "User: input" if is_entry else "User: output"
        content = _ea(hover[:1200])

        # Arrow: from user-box edge to state-box edge (entry) or reverse (exit)
        _hw = _STATE_W // 2
        ax0 = ux  + _hw + _ARR_GAP if is_entry else scx + _hw + _ARR_GAP
        ax1 = scx - _hw - _ARR_GAP if is_entry else ux  - _hw - _ARR_GAP
        if ax1 > ax0 + 2:
            parts.append(
                f'<line x1="{ax0:.1f}" y1="{cy:.1f}" x2="{ax1:.1f}" y2="{cy:.1f}"'
                f' stroke="{_USER_ACTOR_C}" stroke-width="1.5" marker-end="url(#arr)"/>'
            )

        # Box (same dimensions as state boxes, user colour fill)
        bx2 = ux - _hw
        by2 = cy - _STATE_H // 2
        parts.append(
            f'<rect x="{bx2:.1f}" y="{by2:.1f}" width="{_STATE_W}" height="{_STATE_H}"'
            f' rx="3" fill="{_USER_ACTOR_C}" stroke="{_USER_ACTOR_C}"'
            f' data-label="{caption}" data-content="{content}" style="cursor:pointer"/>'
        )
        # Person silhouette in dark ink, scaled to fit inside the box
        head_cy = cy - 5
        parts.extend([
            f'<circle cx="{ux:.1f}" cy="{head_cy:.1f}" r="4"'
            f' fill="#0f172a" pointer-events="none"/>',
            f'<path d="M {ux - 6:.1f},{cy + 4:.1f} A 6,6 0 0 1 {ux + 6:.1f},{cy + 4:.1f} Z"'
            f' fill="#0f172a" pointer-events="none"/>',
        ])

    # ── Phase 3: state boxes (drawn last — on top of everything) ────────────
    for li, lane in enumerate(lanes):
        cy  = lane_cy(li)
        seen_buckets: set[float] = set()
        for el in lane.sequence:
            if not isinstance(el, StateNode):
                continue
            if el.ts in seen_buckets:
                continue
            seen_buckets.add(el.ts)
            scx = cx(el.ts)
            sx2 = scx - _STATE_W // 2
            sy2 = cy  - _STATE_H // 2
            # Use per-lane hover when available; fall back to global hover.
            lane_hover = el.hover_by_lane.get(lane.lane_id, el.hover)
            content  = _ea(lane_hover[:1200])
            sn       = state_num.get(el.ts, "?")
            slabel   = el.label_override or f"S{sn}"
            if el.is_interrupted:
                _sfill   = "#2d1a00"
                _sstroke = "#f59e0b"
                _sdash   = ' stroke-dasharray="4,3"'
                _badge   = '\u26a0'  # ⚠
                _btcolor = "#f59e0b"
            elif el.is_error:
                _sfill   = "#2d0000"
                _sstroke = "#ef4444"
                _sdash   = ' stroke-dasharray="4,3"'
                _badge   = '\u2717'  # ✗
                _btcolor = "#ef4444"
            else:
                _sfill   = _STATE_F
                _sstroke = _STATE_S
                _sdash   = ''
                _badge   = ''
                _btcolor = _STATE_T
            parts += [
                f'<rect x="{sx2:.1f}" y="{sy2:.1f}" width="{_STATE_W}" height="{_STATE_H}"'
                f' rx="3" fill="{_sfill}" stroke="{_sstroke}" stroke-width="1.5"{_sdash}'
                f' data-label="{slabel}" data-content="{content}"'
                f' style="cursor:pointer"/>',
                f'<text x="{scx:.1f}" y="{cy + 4:.1f}" text-anchor="middle"'
                f' font-size="9" font-weight="bold" fill="{_btcolor}"'
                f' pointer-events="none">{slabel}</text>',
            ]
            if _badge:
                # Small badge icon in top-right corner of the state box
                parts.append(
                    f'<text x="{sx2 + _STATE_W - 2:.1f}" y="{sy2 + 7:.1f}"'
                    f' text-anchor="end" font-size="7" fill="{_btcolor}"'
                    f' pointer-events="none">{_badge}</text>'
                )
            # Person-icon user node adjacent to the boundary state (session lane only)
            if show_user_actors and lane.level == "session" and (el.is_user_entry or el.is_user_exit):
                _svg_user_actor(scx, cy, el.is_user_entry, lane_hover)

    # ── Phase 4: instant call icons (on top of state boxes) ─────────────────
    for li, lane in enumerate(lanes):
        cy  = lane_cy(li)
        seen_instant: set[str] = set()
        for el in lane.sequence:
            if not isinstance(el, TransNode) or not el.is_instant:
                continue
            if el.node_id in seen_instant:
                continue
            seen_instant.add(el.node_id)
            gcx  = cx(el.start_ts)
            gw   = _STATE_W
            gh   = _STATE_H
            # Position icon immediately to the right of the state box: state right edge + 4px gap + half icon
            gcx_icon = gcx + _STATE_W // 2 + 4 + _STATE_W // 2
            gx   = gcx_icon - gw // 2
            ty   = cy - gh // 2
            icon = _INSTANT_ICON.get(el.call_type, _INSTANT_ICON_DEFAULT)
            content = _ea((el.hover_in or "(no input)")[:1200])
            parts += [
                f'<rect x="{gx:.1f}" y="{ty:.1f}" width="{gw}" height="{gh}"'
                f' rx="3" fill="{el.color}" stroke="#475569" stroke-width="1.5"'
                f' data-label="{_esc(el.label)}"'
                f' data-content="{content}"'
                f' style="cursor:pointer"/>',
                f'<text x="{gcx_icon:.1f}" y="{cy + 4:.1f}"'
                f' text-anchor="middle" font-size="12"'
                f' fill="#ffffff" pointer-events="none">{icon}</text>',
            ]

    parts.append('</svg>')
    return "\n".join(parts)
