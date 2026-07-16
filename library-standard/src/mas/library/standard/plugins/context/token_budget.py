#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Token-budget trimmer utility for assembled message lists."""

from __future__ import annotations

from typing import Any


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


def _skip_tool_group(tail: list[dict[str, Any]], start: int) -> int:
    """Return how many messages to drop starting at *start* to keep tool pairs intact.

    If ``tail[start]`` is an assistant message with ``tool_calls``, we must also
    drop every subsequent ``tool`` response that references one of those calls.
    If ``tail[start]`` is an orphaned ``tool`` message, drop it too.
    """
    msg = tail[start]
    if msg.get("role") == "assistant" and msg.get("tool_calls"):
        call_ids = {c.get("id") for c in msg["tool_calls"] if c.get("id")}
        count = 1
        while start + count < len(tail):
            nxt = tail[start + count]
            if nxt.get("role") == "tool" and nxt.get("tool_call_id") in call_ids:
                count += 1
            else:
                break
        return count
    if msg.get("role") == "tool":
        return 1
    return 1


def trim_messages_to_budget(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    reserve_tokens: int = 0,
) -> list[dict[str, Any]]:
    """Drop oldest non-system messages until estimated tokens fit the budget.

    Tool-call groups (an assistant message with ``tool_calls`` followed by
    matching ``tool`` responses) are dropped atomically so the resulting list
    never contains orphaned ``tool`` messages.
    """
    if max_tokens <= 0:
        return list(messages)
    budget = max(0, max_tokens - max(0, reserve_tokens))
    if estimate_tokens(messages) <= budget:
        return list(messages)

    pinned: list[dict[str, Any]] = []
    tail = list(messages)
    if tail and tail[0].get("role") == "system":
        pinned.append(tail.pop(0))
    while tail and estimate_tokens(pinned + tail) > budget and len(tail) > 1:
        n = _skip_tool_group(tail, 0)
        if n >= len(tail):
            break
        del tail[:n]
    return pinned + tail
