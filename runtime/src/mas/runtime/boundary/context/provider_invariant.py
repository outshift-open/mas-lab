#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Layer-1 protocol helpers: tool-call / tool-result pairing.

The provider validates ``messages[]`` **structure** (roles, call ids, counts)
before tokenization. It does not parse tool-result text. After an assistant
message that declares tools A and B, the next messages must be those two
results. Full rules for ``ContextManagerContract`` plugins:
``runtime/docs/dev/contracts/state-and-context.md`` (ContextManagerContract).

Slicers should keep a user turn intact (user + everything until the next
user). ``sanitize_provider_messages`` is the last-pass check before send.
"""

from __future__ import annotations

from typing import Any


def tool_call_pairs(messages: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """Return (declared tool_call ids, tool-result ids)."""
    declared = {str(c["id"]) for m in messages if m.get("tool_calls") for c in m["tool_calls"] if c.get("id")}
    returned = {str(m["tool_call_id"]) for m in messages if m.get("role") == "tool" and m.get("tool_call_id")}
    return declared, returned


def start_of_tool_group(messages: list[dict[str, Any]], index: int) -> int:
    """If ``messages[index]`` is a tool result, back up to its assistant.

    Used so a tail slice cannot start on a result with no matching ask.
    """
    if not messages:
        return 0
    i = max(0, min(index, len(messages) - 1))
    while i > 0 and messages[i].get("role") == "tool":
        i -= 1
    return i


def split_user_turns(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split on ``role=user``; each turn is that user plus everything until the next.

    A ReAct loop (assistant asks for tools, results, asks again) under one
    user question stays one turn, so trim/summarize cannot drop the ask and
    keep the answers.
    """
    turns: list[list[dict[str, Any]]] = []
    i = 0
    n = len(messages)
    if i < n and messages[i].get("role") != "user":
        preamble: list[dict[str, Any]] = []
        while i < n and messages[i].get("role") != "user":
            preamble.append(messages[i])
            i += 1
        turns.append(preamble)
    while i < n:
        turn = [messages[i]]
        i += 1
        while i < n and messages[i].get("role") != "user":
            turn.append(messages[i])
            i += 1
        turns.append(turn)
    return turns


def consecutive_tool_result_count(messages: list[dict[str, Any]], assistant_index: int) -> int:
    """How many ``role=tool`` rows follow ``messages[assistant_index]``."""
    n = 0
    j = assistant_index + 1
    while j < len(messages) and messages[j].get("role") == "tool":
        n += 1
        j += 1
    return n


def assert_provider_payload(messages: list[dict[str, Any]]) -> None:
    """Sendable payload: each tool call has exactly one result, immediately after it."""
    declared, returned = tool_call_pairs(messages)
    orphan = returned - declared
    assert not orphan, f"orphan tool results: {orphan}"
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            n_use = len([c for c in msg["tool_calls"] if c.get("id")])
            n_res = consecutive_tool_result_count(messages, i)
            assert n_res == n_use, (
                f"tool results {n_res} != tool calls {n_use} at messages[{i}]"
            )
        if msg.get("role") == "tool":
            prev = messages[i - 1] if i else None
            assert prev is not None, "tool result at start of payload"
            prev_role = prev.get("role")
            assert prev_role in {"assistant", "tool"}, (
                f"tool result at messages[{i}] follows role={prev_role!r}"
            )
            if prev_role == "assistant":
                assert prev.get("tool_calls"), (
                    f"tool result at messages[{i}] follows a text-only assistant"
                )
