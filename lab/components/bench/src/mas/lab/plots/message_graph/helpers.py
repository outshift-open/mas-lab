#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Small helpers for message-graph rendering."""

import html as _html
from typing import Any

def _agent_color(idx: int) -> str:
    return _AGENT_PALETTE[idx % len(_AGENT_PALETTE)]


def _dur_str(start: float, end: float | None) -> str:
    """Human-readable call duration (ms or s)."""
    if end is None or end <= start:
        return "\u2014"
    d = end - start
    return f"{d * 1000:.0f} ms" if d < 1.0 else f"{d:.2f} s"


def _preview(text: Any, n: int = 350) -> str:
    """Truncate text for tooltip display."""
    if not text:
        return "(empty)"
    t = str(text).strip()
    return t if len(t) <= n else t[:n] + "\u2026"


def _tip_attrs(label: str, body: str) -> str:
    """Return data-tip-label + data-tip-body attribute string for SVG elements."""
    le = _html.escape(label, quote=True)
    be = _html.escape(body, quote=True).replace("\n", "&#10;")
    return f' data-tip-label="{le}" data-tip-body="{be}"'

