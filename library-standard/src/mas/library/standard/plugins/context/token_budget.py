#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Assembly token trim — tool-group-aware (enabled via context_manager.params.trimmer)."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


def _estimate_tokens_lists(*parts: list[dict[str, Any]]) -> int:
    char_total = 0
    msg_count = 0
    for msgs in parts:
        for m in msgs:
            msg_count += 1
            content = m.get("content", "")
            if isinstance(content, str):
                char_total += len(content)
            for call in m.get("tool_calls") or []:
                fn = call.get("function") or {}
                char_total += len(str(fn.get("name", ""))) + len(str(fn.get("arguments", "")))
    return char_total // 4 + msg_count * 4


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    return _estimate_tokens_lists(messages)


def _oldest_group_size(msgs: list[dict[str, Any]]) -> int:
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


def _sync_pin_tail_after_assistant_drop(
    first: dict[str, Any],
    pinned_tail: list[dict[str, Any]],
) -> None:
    if first.get("role") != "assistant" or not first.get("tool_calls"):
        return
    call_ids = {str(c.get("id")) for c in first["tool_calls"] if c.get("id")}
    while pinned_tail and pinned_tail[0].get("role") == "tool":
        tid = str(pinned_tail[0].get("tool_call_id") or "")
        if tid in call_ids:
            pinned_tail.pop(0)
            call_ids.discard(tid)
        else:
            break


def trim_messages_to_budget(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    reserve_tokens: int = 0,
    pin_tail: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if max_tokens <= 0:
        return list(messages) + list(pin_tail or [])
    budget = max(0, max_tokens - max(0, reserve_tokens))
    pinned_tail = list(pin_tail or [])
    if _estimate_tokens_lists(messages, pinned_tail) <= budget:
        return list(messages) + pinned_tail

    head: list[dict[str, Any]] = []
    tail = list(messages)
    if tail and tail[0].get("role") == "system":
        head.append(tail.pop(0))
    total = _estimate_tokens_lists(head, tail, pinned_tail)
    while tail and total > budget and len(tail) > 1:
        n = _oldest_group_size(tail)
        if n >= len(tail):
            break
        first = tail[0]
        del tail[:n]
        _sync_pin_tail_after_assistant_drop(first, pinned_tail)
        total = _estimate_tokens_lists(head, tail, pinned_tail)

    while pinned_tail and total > budget:
        n = _oldest_group_size(pinned_tail)
        if n >= len(pinned_tail):
            break
        del pinned_tail[:n]
        total = _estimate_tokens_lists(head, tail, pinned_tail)

    result: list[dict[str, Any]] = []
    result.extend(head)
    result.extend(tail)
    result.extend(pinned_tail)
    over = _estimate_tokens_lists(result)
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
