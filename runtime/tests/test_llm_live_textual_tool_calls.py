#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Regression tests for textual tool-call markup fallback parsing."""

from __future__ import annotations

import json

from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.engine.textual_tool_calls import (
    _build_tool_schemas,
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


def _query_db_tool_def() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "query_db",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "query_type": {
                        "type": "string",
                        "enum": ["pg_stat_activity", "blocking_queries", "deadlocks", "connection_pool"],
                    },
                },
            },
        },
    }


def _get_deployments_tool_def() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "get_deployments",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "limit": {"type": "integer"},
                    "window": {"type": "string"},
                },
            },
        },
    }


def test_recover_tool_calls_from_content_maps_bare_enum_value_onto_its_parameter() -> None:
    # A backend emits a bare positional arg instead of `query_type="blocking_queries"`.
    # Regression: yaml.safe_load(\"{blocking_queries}\") used to parse this as
    # {"blocking_queries": None} (YAML flow-mapping shorthand for a bare key),
    # producing a phantom key instead of landing the value on query_type.
    content = "query_db(blocking_queries)"

    tool_calls, _cleaned = recover_tool_calls_from_content(
        content,
        known_tool_names={"query_db"},
        tool_schemas={"query_db": _build_tool_schemas([_query_db_tool_def()])["query_db"]},
    )

    assert len(tool_calls) == 1
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert args == {"query_type": "blocking_queries"}


def test_recover_tool_calls_from_content_maps_bare_value_onto_next_free_parameter() -> None:
    # Mixed call: a bare positional arg alongside a keyed one, e.g. the backend
    # meant get_deployments(service="payment-service", window="24h") but wrote
    # the service name bare. Previously this produced
    # {"payment-service": None, "window": "24h"}.
    content = "get_deployments(payment-service, window: '24h')"

    tool_calls, _cleaned = recover_tool_calls_from_content(
        content,
        known_tool_names={"get_deployments"},
        tool_schemas={"get_deployments": _build_tool_schemas([_get_deployments_tool_def()])["get_deployments"]},
    )

    assert len(tool_calls) == 1
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert args == {"service": "payment-service", "window": "24h"}


def test_recover_tool_calls_from_content_falls_back_to_value_key_without_schema() -> None:
    # No tool schema available at all -- must not silently null the value out.
    content = "get_metrics(payment-service)"

    tool_calls, _cleaned = recover_tool_calls_from_content(content, known_tool_names={"get_metrics"})

    assert len(tool_calls) == 1
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert args == {"value": "payment-service"}


def test_multiline_bare_json_call_is_unaffected_by_positional_arg_handling() -> None:
    content = 'run_skill_script({\n  "skill": "demo",\n  "args": ["record", "item-1"]\n})'

    tool_calls, cleaned = recover_tool_calls_from_content(
        content,
        known_tool_names={"run_skill_script"},
    )

    assert len(tool_calls) == 1
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert args == {"skill": "demo", "args": ["record", "item-1"]}
    assert cleaned == ""


def test_xml_named_tool_tags_recover_delegate_calls() -> None:
    content = """I'm ready.

<delegate_to_finance>
ROUND=1;TARGET=finance;

User message:
hello
</delegate_to_finance>

<delegate_to_customer_success>
ROUND=1;TARGET=customer_success;
task two
</delegate_to_customer_success>
"""
    tool_calls, leftover = recover_tool_calls_from_content(
        content,
        known_tool_names={"delegate_to_finance", "delegate_to_customer_success"},
    )

    assert [c["function"]["name"] for c in tool_calls] == [
        "delegate_to_finance",
        "delegate_to_customer_success",
    ]
    first_args = json.loads(tool_calls[0]["function"]["arguments"])
    assert first_args["task"].startswith("ROUND=1;TARGET=finance;")
    assert "delegate_to_finance" not in leftover
