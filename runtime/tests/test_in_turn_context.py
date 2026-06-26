#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Working memory + registry-backed context assembly (kernel path)."""

from __future__ import annotations

from unittest.mock import MagicMock

from mas.library.standard.plugins.context.token_budget import trim_messages_to_budget
from mas.runtime.boundary.context.assemble import assemble_llm_messages
from mas.runtime.boundary.context.working_memory import SOURCE_TYPE, WorkingMemoryStore
from mas.runtime.contracts.cm_factory import CMFactory
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.driver.driver import KernelDriver
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.driver.mocks import AutoCtxAssembler
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


def test_working_memory_source_type():
    assert SOURCE_TYPE == "working_memory"


def test_default_cm_is_sliding_window():
    cm = CMFactory.create(manifest={})
    assert cm.__class__.__name__ == "SlidingWindowConversation"


def test_cm_assembly_includes_working_memory_after_user():
    ctx = AutoCtxAssembler(last_user_text="Who is POTUS?")
    ctx.record_assistant_tool_call(call_id="call_1", tool_name="web-search", arguments={"q": "POTUS"})
    ctx.record_tool_result(call_id="call_1", content="Donald Trump is president.")
    messages = assemble_llm_messages(ctx)
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]


def test_build_messages_includes_tool_results():
    ctx = AutoCtxAssembler(last_user_text="Who is current POTUS?")
    ctx.record_assistant_tool_call(call_id="call_1", tool_name="web-search", arguments={"q": "POTUS"})
    ctx.record_tool_result(call_id="call_1", content="Donald Trump is president.")
    engine = LiveLlmEngine(ctx=ctx, manifest={"spec": {"tools": ["web-search"]}})
    msgs = engine._build_messages()
    assert any(m["role"] == "tool" for m in msgs)
    assert msgs[-1]["role"] == "tool"


def test_driver_records_working_memory():
    ctx = AutoCtxAssembler()
    driver = KernelDriver(kernel=MagicMock(), engine=MagicMock(), ctx=ctx)
    driver._record_working_memory(
        InvokeEngineIo(correlation_id=7, op="LLM_CALL"),
        EngineIoReturn(
            correlation_id=7,
            response_kind="MODEL_TEXT",
            next_step="TOOL_CALL",
            tool_name="web-search",
            tool_arguments={"query": "POTUS"},
            text="",
        ),
    )
    assert ctx.working_memory.messages[0]["tool_calls"][0]["id"] == "call_7"


def test_parallel_tool_calls_single_assistant_message():
    store = WorkingMemoryStore()
    store.record_assistant_tool_calls(
        [("call_10", "web-search", {"q": "a"}), ("call_11", "calculator", {"expression": "1+1"})]
    )
    assert len(store.messages[0]["tool_calls"]) == 2


def test_token_budget_trimmer():
    messages = [{"role": "system", "content": "x" * 50}]
    messages.extend({"role": "user", "content": "y" * 3000} for _ in range(10))
    trimmed = trim_messages_to_budget(messages, max_tokens=200, reserve_tokens=50)
    assert len(trimmed) < len(messages)


def test_tool_result_binds_to_llm_call_id_not_tool_egress_id():
    """Regression: tool egress correlation_id differs from LLM correlation_id."""
    ctx = AutoCtxAssembler()
    driver = KernelDriver(kernel=MagicMock(), engine=MagicMock(), ctx=ctx)
    driver._record_working_memory(
        InvokeEngineIo(correlation_id=3, op="LLM_CALL"),
        EngineIoReturn(
            correlation_id=3,
            response_kind="MODEL_TEXT",
            next_step="TOOL_CALL",
            tool_name="web-search",
            tool_arguments={"query": "POTUS"},
            text="",
        ),
    )
    driver._record_working_memory(
        InvokeEngineIo(correlation_id=2, op="TOOL_CALL"),
        EngineIoReturn(
            correlation_id=2,
            response_kind="TOOL_RESULT",
            next_step="LLM_CALL",
            text="Donald Trump is president.",
        ),
    )
    from mas.runtime.schema.ingress import EngineIoReturn as EIR

    driver._sync_tool_result_memory(
        EIR(
            correlation_id=2,
            response_kind="TOOL_RESULT",
            next_step="LLM_CALL",
            text="Donald Trump is president.",
        )
    )
    assistant = ctx.working_memory.messages[0]
    tool_msg = ctx.working_memory.messages[1]
    assert assistant["tool_calls"][0]["id"] == "call_3"
    assert tool_msg["tool_call_id"] == "call_3"


def test_react_loop_second_llm_sees_tool_result():
    ctx = AutoCtxAssembler()
    rounds = {"n": 0}

    class ScriptEngine:
        def exchange_preview(self, op: str) -> str:
            return op

        def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
            if io.op == "LLM_CALL":
                rounds["n"] += 1
                if rounds["n"] == 1:
                    return EngineIoReturn(
                        correlation_id=io.correlation_id,
                        response_kind="MODEL_TEXT",
                        next_step="TOOL_CALL",
                        tool_name="web-search",
                        tool_arguments={"query": "POTUS"},
                        text="",
                    )
                assert any(m.get("role") == "tool" for m in ctx.working_memory.messages)
                return EngineIoReturn(
                    correlation_id=io.correlation_id,
                    response_kind="MODEL_TEXT",
                    next_step="STOP",
                    text="Donald Trump is the current President.",
                )
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="TOOL_RESULT",
                next_step="LLM_CALL",
                text="results",
            )

        def set_scheduled_tool(self, name: str, arguments: dict | None = None) -> None:
            pass

    trace = RuntimeInstance.from_parts(ctx=ctx, engine=ScriptEngine()).run_user_text(  # type: ignore[arg-type]
        "Who is current POTUS?",
    )
    assert rounds["n"] == 2


def test_turn_commit_preserves_tool_trajectory_for_follow_up():
    ctx = AutoCtxAssembler()
    ctx.note_user_input("Who is POTUS?")
    ctx.record_assistant_tool_call(call_id="call_1", tool_name="web-search", arguments={"query": "POTUS"})
    ctx.record_tool_result(call_id="call_1", content='[{"body": "Donald Trump is the 47th president."}]')
    ctx.record_assistant_message("Donald Trump is the current President.")
    ctx.note_agent_response("Donald Trump is the current President.")

    ctx.note_user_input("Why did you say Biden?")
    messages = assemble_llm_messages(ctx)
    roles = [m["role"] for m in messages]
    assert roles.count("tool") == 1
    assert "assistant" in roles
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Why did you say Biden?"
