#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Live LLM tool payload — ReAct keeps tools after tool results."""

from __future__ import annotations

from mas.runtime.boundary.context.assemble import llm_request_tools, llm_tool_choice


def test_request_tools_kept_after_tool_results() -> None:
    messages = [
        {"role": "user", "content": "Who is POTUS?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1"}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "Current is Example Person"},
    ]
    tools = [{"type": "function", "function": {"name": "web-search"}}]
    assert llm_request_tools(messages, tools=tools) == tools
    assert llm_tool_choice(messages, tools=tools) == "auto"


def test_request_tools_included_without_tool_results() -> None:
    messages = [{"role": "user", "content": "Who is POTUS?"}]
    tools = [{"type": "function", "function": {"name": "web-search"}}]
    assert llm_request_tools(messages, tools=tools) == tools
    assert llm_tool_choice(messages, tools=tools) == "auto"


def test_request_tools_none_when_no_tools() -> None:
    messages = [{"role": "tool", "tool_call_id": "call_1", "content": "x"}]
    assert llm_request_tools(messages, tools=None) is None
    assert llm_request_tools(messages, tools=[]) is None
