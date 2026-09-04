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


def _system_tool_specs() -> list:
    """request_human_input/inform_user, shaped as they're actually auto-injected
    onto every agent (see manifest_tool_provider._inject_system_tools) -- neither
    has an "expression" or "query" property, so the fallback branch is what's
    under test here."""
    return [
        (
            "request_human_input",
            {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "question_type": {"type": "string"},
                    "choices": {"type": "array"},
                    "context_data": {"type": "object"},
                    "timeout": {"type": "number"},
                },
                "required": ["question"],
            },
        ),
        ("inform_user", {"type": "object", "properties": {"message": {"type": "string"}}}),
    ]


def test_pick_tool_call_skips_system_tools_in_favor_of_a_real_tool():
    """Regression: request_human_input/inform_user are unconditionally present
    on every agent's tool list (including delegates), so the "nothing else
    matched" fallback used to always pick request_human_input (list index 0)
    instead of the agent's own real tool -- a mocked delegate would call
    request_human_input and get auto-resolved instead of doing its actual job."""
    specs = _system_tool_specs() + [
        (
            "lookup_schedule",
            {
                "type": "object",
                "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}},
                "required": ["origin", "destination"],
            },
        )
    ]
    name, _args = pick_tool_call("Find a route from Celestia to Verdantia", specs) or ("", {})
    assert name == "lookup_schedule"


def test_pick_tool_call_falls_back_to_a_system_tool_when_nothing_else_exists():
    name, _args = pick_tool_call("anything", _system_tool_specs()) or ("", {})
    assert name == "request_human_input"
