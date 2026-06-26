#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Delegation highlight resolution."""

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Highlight helpers
# ---------------------------------------------------------------------------

def _resolve_highlights(
    delegations: list[dict],
    highlights: list[str] | None,
) -> set[int]:
    """Return 0-based indices into *delegations* that match *highlights*.

    Each entry in *highlights* is either:
    - A numeric string ("1", "3") → 1-based index into the list.
    - A non-numeric string          → prefix-match against correlation_id.
    """
    if not highlights:
        return set()
    result: set[int] = set()
    for h in highlights:
        h = str(h).strip()
        if h.isdigit():
            idx = int(h) - 1
            if 0 <= idx < len(delegations):
                result.add(idx)
        else:
            for i, d in enumerate(delegations):
                cid = d.get("correlation_id") or ""
                if cid.startswith(h):
                    result.add(i)
    return result


def _resolve_keyword_highlights(
    delegations: list[dict],
    keywords: list[str] | None,
) -> set[int]:
    """Return 0-based indices into *delegations* whose task or output contains
    any of *keywords* (case-insensitive)."""
    if not keywords:
        return set()
    kws = [k.lower() for k in keywords]
    result: set[int] = set()
    for i, d in enumerate(delegations):
        text = (d.get("task", "") + " " + d.get("output", "")).lower()
        if any(kw in text for kw in kws):
            result.add(i)
    return result
