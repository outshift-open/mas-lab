#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mock LLM cache and schema-driven tool selection."""

from __future__ import annotations

from mas.library.standard.mock_llm import openai_tools_to_specs, pick_tool_call, stub_arguments
from mas.library.standard.plugins.llm_mock import MockModelAccess


def test_pick_tool_call_uses_expression_schema():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "arith-eval",
                "parameters": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        }
    ]
    specs = openai_tools_to_specs(tools)
    name, args = pick_tool_call("What is 2+2?", specs) or ("", {})
    assert name == "arith-eval"
    assert args["expression"] == "2+2"


def test_mock_model_access_returns_tool_call_for_arithmetic_prompt():
    access = MockModelAccess()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "arith-eval",
                "parameters": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        }
    ]
    msg = access.chat_completion(
        model="mock",
        messages=[{"role": "user", "content": "Compute 3 * 7"}],
        tools=tools,
    )
    assert msg.get("tool_calls")
    assert msg["tool_calls"][0]["function"]["name"] == "arith-eval"


def test_stub_arguments_fills_required_string():
    params = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    args = stub_arguments(params, "weather in Paris")
    assert args["query"] == "weather in Paris"
