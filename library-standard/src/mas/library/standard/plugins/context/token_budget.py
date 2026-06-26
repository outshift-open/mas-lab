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


def trim_messages_to_budget(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    reserve_tokens: int = 0,
) -> list[dict[str, Any]]:
    """Drop oldest non-system messages until estimated tokens fit the budget."""
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
        tail.pop(0)
    return pinned + tail
