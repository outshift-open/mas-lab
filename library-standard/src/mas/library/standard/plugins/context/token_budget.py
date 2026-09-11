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


def trim_messages_to_budget(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    reserve_tokens: int = 0,
    pin_tail: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Drop oldest non-system messages until estimated tokens fit the budget.

    ``pin_tail`` is appended after trimming and never removed. Assembly uses
    this for structurally pinned in-turn working memory while outbound waits are
    active on the kernel ledger.
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
    result = head + tail + pinned_tail
    over = estimate_tokens(result)
    if over > budget:
        _log.warning(
            "token budget %d exceeded by pinned messages alone (~%d tokens, "
            "%d pinned tail message(s)): raise the context budget or reduce "
            "what is injected into the prompt",
            budget,
            over,
            len(pinned_tail),
        )
    return result
