#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for shared LLM cache helpers."""

from __future__ import annotations

from mas.runtime.engine.llm_cache import assistant_message_from_cache_content, llm_cache_key


def test_llm_cache_key_includes_tools():
    messages = [{"role": "user", "content": "hi"}]
    without_tools = llm_cache_key("mock", messages, None)
    with_tools = llm_cache_key(
        "mock",
        messages,
        [{"type": "function", "function": {"name": "tool-a"}}],
    )
    assert without_tools != with_tools


def test_assistant_message_from_cache_content_parses_tool_calls():
    raw = '{"tool_calls": [{"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}]}'
    msg = assistant_message_from_cache_content(raw)
    assert msg is not None
    assert msg["content"] is None
    assert msg["tool_calls"][0]["function"]["name"] == "t"
