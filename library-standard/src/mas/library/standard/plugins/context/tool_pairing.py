#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared helpers for trimming message lists without splitting tool_calls/tool pairs."""

from __future__ import annotations

from typing import Any


def skip_tool_group(messages: list[dict[str, Any]], start: int) -> int:
    """Return how many messages to drop starting at *start* to keep tool pairs intact.

    If ``messages[start]`` is an assistant message with ``tool_calls``, every
    subsequent ``tool`` response that references one of those calls is dropped
    with it. An orphaned ``tool`` message is dropped alone.
    """
    msg = messages[start]
    if msg.get("role") == "assistant" and msg.get("tool_calls"):
        call_ids = {c.get("id") for c in msg["tool_calls"] if c.get("id")}
        count = 1
        while start + count < len(messages):
            nxt = messages[start + count]
            if nxt.get("role") == "tool" and nxt.get("tool_call_id") in call_ids:
                count += 1
            else:
                break
        return count
    return 1


def group_exchanges(past: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group messages into user/assistant exchanges, keeping tool_calls/tool pairs atomic."""
    exchanges: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(past):
        msg = past[i]
        if msg.get("role") == "user":
            exchange = [msg]
            i += 1
            if i < len(past) and past[i].get("role") == "assistant":
                exchange.append(past[i])
                i += 1
                n = skip_tool_group(past, i - 1) - 1  # trailing tool results, if any
                exchange.extend(past[i : i + n])
                i += n
            exchanges.append(exchange)
        else:
            n = skip_tool_group(past, i)
            exchanges.append(past[i : i + n])
            i += n
    return exchanges
