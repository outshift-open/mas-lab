#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Provider payload repair for committed history after trimming (PR #55 regressions)."""

from __future__ import annotations

from typing import Any

from mas.library.standard.plugins.context.assembler import ContextAssemblerPlugin
from mas.library.standard.plugins.context.conversation import (
    SlidingWindowConversation,
    StackConversation,
    SummarizingConversation,
)
from mas.library.standard.plugins.context.provider_payload import (
    assert_provider_payload,
    sanitize_provider_messages,
    tool_call_pairs,
)
from mas.library.standard.plugins.context.token_budget import trim_messages_to_budget


def _tool_turn(call_id: str = "call_1", *, content: str = "result") -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "ask"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "function": {"name": "f", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": call_id, "content": content},
        {"role": "assistant", "content": "done"},
    ]


def test_sanitize_drops_orphan_tool_message() -> None:
    out = sanitize_provider_messages(
        [
            {"role": "tool", "tool_call_id": "missing", "content": "orphan"},
            {"role": "user", "content": "hi"},
        ]
    )
    assert out == [{"role": "user", "content": "hi"}]


def test_sanitize_strips_incomplete_assistant_tool_calls() -> None:
    out = sanitize_provider_messages(
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "f", "arguments": "{}"}}],
            },
            {"role": "user", "content": "follow up"},
        ]
    )
    assert out == [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": "follow up"},
    ]


def test_sanitize_preserves_complete_tool_exchange() -> None:
    out = sanitize_provider_messages(_tool_turn())
    assert_provider_payload(out)


def test_sanitize_rebinds_hitl_steering_tool_to_preceding_assistant() -> None:
    out = sanitize_provider_messages(
        [
            {"role": "user", "content": "Who is POTUS?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "search", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "call_3", "content": "Maxence Postu is POTUS"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_4", "function": {"name": "search", "arguments": "{}"}}],
            },
            {"role": "user", "content": "Follow-up?"},
        ]
    )
    tool_msgs = [m for m in out if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert_provider_payload(out)


def test_stack_trim_plus_sanitize_is_provider_safe() -> None:
    past = _tool_turn("call_0") + _tool_turn("call_1")
    trimmed = StackConversation(max_messages=3).manage_history(past, budget_tokens=0)
    out = sanitize_provider_messages(trimmed)
    assert_provider_payload(out)


def test_sliding_window_plus_sanitize_is_provider_safe() -> None:
    past: list[dict[str, Any]] = []
    for i in range(6):
        past.extend(_tool_turn(f"call_{i}"))
    trimmed = SlidingWindowConversation(max_turns=1).manage_history(past, budget_tokens=0)
    out = sanitize_provider_messages(trimmed)
    assert_provider_payload(out)


def test_summarizing_conversation_plus_sanitize_is_provider_safe() -> None:
    past: list[dict[str, Any]] = []
    for i in range(6):
        past.extend(_tool_turn(f"call_{i}"))
    cm = SummarizingConversation(
        summary_threshold=1,
        keep_turns=1,
        summarize_fn=lambda msgs: "summary of earlier turns",
    )
    trimmed = cm.manage_history(past, budget_tokens=0)
    out = sanitize_provider_messages(trimmed)
    assert_provider_payload(out)


def test_trim_with_structural_pin_tail() -> None:
    history = [{"role": "user", "content": "x" * 5000} for _ in range(8)]
    wm = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_wm", "function": {"name": "f", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_wm", "content": "live"},
    ]
    out = trim_messages_to_budget(history, max_tokens=400, pin_tail=wm)
    assert out[-2:] == wm
    assert_provider_payload(out)


# --- PR #55 Bedrock-style regressions (orphan tool at slice boundary) ---


def test_pr55_stack_slice_orphan_tool_at_front() -> None:
    """Stack trim can leave a lone tool message — sanitize must drop it."""
    past = _tool_turn("call_0") + _tool_turn("call_1")
    trimmed = StackConversation(max_messages=2).manage_history(past, budget_tokens=0)
    assert trimmed[0]["role"] == "tool"
    assert not any(m.get("tool_calls") for m in trimmed)
    out = sanitize_provider_messages(trimmed)
    assert not any(m.get("role") == "tool" for m in out)
    assert_provider_payload(out)


def test_pr55_stack_various_max_messages_never_violate_invariant() -> None:
    past: list[dict[str, Any]] = []
    for i in range(10):
        past.extend(_tool_turn(f"call_{i}"))
    for max_msgs in range(1, 20):
        trimmed = StackConversation(max_messages=max_msgs).manage_history(past, budget_tokens=0)
        out = sanitize_provider_messages(trimmed)
        declared, returned = tool_call_pairs(out)
        assert returned <= declared
        assert_provider_payload(out)


def test_pr55_sliding_window_split_exchange() -> None:
    past: list[dict[str, Any]] = []
    for i in range(8):
        past.extend(_tool_turn(f"call_{i}"))
    trimmed = SlidingWindowConversation(max_turns=2).manage_history(past, budget_tokens=0)
    out = sanitize_provider_messages(trimmed)
    assert_provider_payload(out)


def test_pr55_token_budget_many_sizes_on_tool_history() -> None:
    past: list[dict[str, Any]] = []
    for i in range(6):
        past.extend(_tool_turn(f"call_{i}", content=f"payload-{i}-" + "x" * 200))
    for budget in (50, 100, 200, 400, 800, 1600, 3200):
        out = trim_messages_to_budget(past, max_tokens=budget)
        out = sanitize_provider_messages(out)
        assert_provider_payload(out)


def test_pr55_assembler_end_to_end_with_live_tool_exchange() -> None:
    plugin = ContextAssemblerPlugin(conversation_strategy=StackConversation(max_messages=6))
    history = _tool_turn("call_0") + _tool_turn("call_1") + _tool_turn("call_2")
    history.append({"role": "user", "content": "current question"})
    history.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_live", "function": {"name": "f", "arguments": "{}"}}],
        }
    )
    out = plugin._apply_conversation_strategy(history)
    declared, returned = tool_call_pairs(out)
    assert "call_live" in declared
    assert returned <= declared
    assert_provider_payload(out)
