#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Regression tests for textual tool-call markup fallback parsing."""

from __future__ import annotations

from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.engine.textual_tool_calls import (
    recover_tool_calls_from_content,
    repair_merged_arg_keys,
    strip_channel_markup,
)
from mas.runtime.schema.egress import InvokeEngineIo


def test_strip_channel_markup_removes_channel_tokens() -> None:
    text = "<|channel>thought\n<channel|>I recommend 20%."
    assert strip_channel_markup(text) == "I recommend 20%."


def test_strip_channel_markup_handles_sentinel_only_output() -> None:
    assert strip_channel_markup("<|channel>thought") == ""


def test_recover_tool_calls_from_content_parses_multiple_calls() -> None:
    content = (
        '<|tool_call>call:activate_skill(name:<|"|>evidence-grounded-specialist<|"|>)<tool_call|>'
        '<|tool_call>call:query_salesforce_opportunity(account_name:<|"|>Acme<|"|>)<tool_call|>'
    )

    tool_calls, cleaned = recover_tool_calls_from_content(content)

    assert cleaned == ""
    assert [item["function"]["name"] for item in tool_calls] == [
        "activate_skill",
        "query_salesforce_opportunity",
    ]
    assert '"account_name": "Acme"' in tool_calls[1]["function"]["arguments"]


def test_recover_tool_calls_from_content_parses_multiline_bare_call() -> None:
    content = 'run_skill_script({\n  "skill": "demo",\n  "args": ["record", "item-1"]\n})'

    tool_calls, cleaned = recover_tool_calls_from_content(
        content,
        known_tool_names={"run_skill_script"},
    )

    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "run_skill_script"
    assert '"skill": "demo"' in tool_calls[0]["function"]["arguments"]
    assert cleaned == ""


def test_repair_merged_arg_keys_splits_glued_array_key() -> None:
    repaired = repair_merged_arg_keys(
        {
            'args=["record", "item-1"],script': "runner.py",
            "skill": "demo",
        }
    )

    assert repaired == {
        "args": ["record", "item-1"],
        "script": "runner.py",
        "skill": "demo",
    }


def test_live_engine_uses_textual_tool_call_fallback_for_tool_loop() -> None:
    engine = LiveLlmEngine(use_tool_loop=True, use_cache=False)
    io = InvokeEngineIo(correlation_id=7, op="LLM_CALL")
    message = {
        "role": "assistant",
        "content": '<|tool_call>call:activate_skill(name:<|"|>demo-answer-metadata-format<|"|>)<tool_call|>',
    }

    ret = engine._message_to_engine_return(
        io,
        message,
        [{"role": "user", "content": "hi"}],
        [],
        False,
        {},
        "stop",
    )

    assert ret.next_step == "TOOL_CALL"
    assert ret.tool_name == "activate_skill"
    assert ret.tool_arguments == {"name": "demo-answer-metadata-format"}


def test_recover_tool_calls_from_content_parses_bare_tool_plan_with_variable_binding() -> None:
    content = '- salesforce_agent_raw: "hello world"\n- sanitize_demo_metadata(salesforce_agent_raw)'

    tool_calls, _cleaned = recover_tool_calls_from_content(content)

    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "sanitize_demo_metadata"
    assert '"value": "hello world"' in tool_calls[0]["function"]["arguments"]
