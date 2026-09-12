#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Token-budget trimmer utility for assembled message lists."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content)
        for call in m.get("tool_calls") or []:
            fn = call.get("function") or {}
            total += len(str(fn.get("name", ""))) + len(str(fn.get("arguments", "")))
    return total // 4 + len(messages) * 4


def _oldest_group_size(msgs: list[dict[str, Any]]) -> int:
    """Size of the tool-call group starting at ``msgs[0]`` (>=1)."""
    if not msgs:
        return 0
    first = msgs[0]
    if first.get("role") == "assistant" and first.get("tool_calls"):
        call_ids = {c.get("id") for c in first["tool_calls"] if c.get("id")}
        n = 1
        while n < len(msgs) and msgs[n].get("role") == "tool" and msgs[n].get("tool_call_id") in call_ids:
            n += 1
        return n
    return 1


# ``pin_tail`` in :func:`trim_messages_to_budget` is the structurally *pinned*
# in-turn working-memory slice from :mod:`mas.runtime.boundary.context.assemble`.
# See that module's docstring for how pinning differs from the WM count cap.


def trim_messages_to_budget(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    reserve_tokens: int = 0,
    pin_tail: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Drop oldest non-system messages until estimated tokens fit the budget.

    ``pin_tail`` (structurally pinned in-turn working memory) is appended
    after trimming ``messages``. It is *not* exempt from the budget: once
    ``messages`` is fully trimmed and the budget is still exceeded, the
    oldest tool-call group is dropped from ``pin_tail`` too — atomically, so
    an assistant's ``tool_calls`` never end up separated from their ``tool``
    results — always keeping at least the most recent group (the model's
    latest action must stay visible). Only if that single most-recent group
    alone still exceeds the budget is the overflow logged instead of dropped.
    """
    if max_tokens <= 0:
        return list(messages) + list(pin_tail or [])
    budget = max(0, max_tokens - max(0, reserve_tokens))
    pinned_tail = list(pin_tail or [])
    if estimate_tokens(messages + pinned_tail) <= budget:
        return list(messages) + pinned_tail

    head: list[dict[str, Any]] = []
    tail = list(messages)
    if tail and tail[0].get("role") == "system":
        head.append(tail.pop(0))
    while tail and estimate_tokens(head + tail + pinned_tail) > budget and len(tail) > 1:
        del tail[0]

    while pinned_tail and estimate_tokens(head + tail + pinned_tail) > budget:
        n = _oldest_group_size(pinned_tail)
        if n >= len(pinned_tail):
            break  # never drop the last remaining (most recent) group
        del pinned_tail[:n]

    result = head + tail + pinned_tail
    over = estimate_tokens(result)
    if over > budget:
        _log.warning(
            "token budget %d exceeded by the most recent pinned tool-call "
            "group alone (~%d tokens, %d pinned tail message(s)): raise the "
            "context budget or reduce what is injected into the prompt",
            budget,
            over,
            len(pinned_tail),
        )
    return result
