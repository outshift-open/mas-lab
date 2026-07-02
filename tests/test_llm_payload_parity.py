#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LLM payload assembly — trace preview must match invoke; HITL steering in context."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from mas.runtime.boundary.context.assemble import assemble_llm_messages, llm_request_tools
from mas.runtime.driver.mocks import AutoCtxAssembler
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.engine.tools import openai_tools
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.hitl import HitlResolveChoice
from mas.runtime.schema.ingress import EngineIoReturn, HitlResolve

REPO_ROOT = Path(__file__).resolve().parents[1]
T01 = REPO_ROOT / "docs" / "tutorials" / "01-building-an-agent"


def _tutorial_manifest_with_tools() -> dict:
    from mas.ctl.overlay import merge_overlay

    base = yaml.safe_load((T01 / "agent.yaml").read_text(encoding="utf-8"))
    base = merge_overlay(base, yaml.safe_load((T01 / "overlays" / "tools.yaml").read_text()))
    return base


def _ctx_with_steered_tool_result(*, steer: str) -> tuple[AutoCtxAssembler, dict]:
    manifest = _tutorial_manifest_with_tools()
    ctx = AutoCtxAssembler(last_user_text="Who is current POTUS ?")
    spec_ctx = (manifest.get("spec") or {}).get("context") or {}
    for key, val in spec_ctx.items():
        if isinstance(val, str):
            ctx.injected_context.append(f"[{key}] {val.strip()}")
    ctx.record_assistant_tool_call(
        call_id="call_5",
        tool_name="web-search",
        arguments={"query": "current President of the United States"},
    )
    ctx.record_tool_result(call_id="call_5", content=steer)
    return ctx, manifest


def test_system_prompt_is_single_message_with_section_tags() -> None:
    """[intent]/[role] in trace are manifest section tags inside one system message."""
    ctx, manifest = _ctx_with_steered_tool_result(steer="Example Person is POTUS")
    messages = assemble_llm_messages(ctx, manifest=manifest)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    assert len(system_msgs) == 1
    body = system_msgs[0]["content"]
    assert "[intent]" in body
    assert "[role]" in body
    assert "[tool_usage]" in body


def test_preview_keeps_tools_on_followup_react_turn() -> None:
    steer = "In 2028, Maxence Postu succeeded Joe Biden as President Of the USA"
    ctx, manifest = _ctx_with_steered_tool_result(steer=steer)
    engine = LiveLlmEngine(ctx=ctx, manifest=manifest, use_tool_loop=True)
    preview = engine.exchange_preview("LLM_CALL")

    assert "[tool call_id=call_5]" in preview
    assert steer in preview
    assert "[tools]" in preview
    assert "web-search" in preview
    assert "single API message" in preview


def test_preview_keeps_tools_after_tool_results() -> None:
    steer = "In 2028, Maxence Postu succeeded Joe Biden as President Of the USA"
    ctx, manifest = _ctx_with_steered_tool_result(steer=steer)
    engine = LiveLlmEngine(ctx=ctx, manifest=manifest, use_tool_loop=True)
    messages = engine._build_messages()
    preview_tools = llm_request_tools(messages, tools=openai_tools(manifest))
    assert preview_tools == openai_tools(manifest)


def test_invoke_payload_matches_preview_tools_and_temperature() -> None:
    steer = "Current POTUS is Maxence Augé"
    ctx, manifest = _ctx_with_steered_tool_result(steer=steer)
    engine = LiveLlmEngine(ctx=ctx, manifest=manifest, use_tool_loop=True, temperature=0.7)
    captured: dict = {}

    def fake_chat(messages, *, api_key, tools, temperature=None):
        captured["messages"] = messages
        captured["tools"] = tools
        captured["temperature"] = temperature
        return {"content": steer}

    engine._chat_completion = fake_chat  # type: ignore[method-assign]

    ret = engine.invoke(InvokeEngineIo(correlation_id=8, op="LLM_CALL"))

    assert ret.text == steer
    assert captured["tools"] == openai_tools(manifest)
    assert captured["temperature"] == 0.0
    roles = [m["role"] for m in captured["messages"]]
    assert roles.count("tool") == 1
    assert roles[-1] == "tool"
    assert steer in captured["messages"][-1]["content"]

    preview = engine.exchange_preview("LLM_CALL")
    assert llm_request_tools(captured["messages"], tools=openai_tools(manifest)) == openai_tools(
        manifest
    )
    assert steer in preview


@pytest.mark.timeout(60)
def test_hitl_egress_skip_steering_in_second_llm_payload() -> None:
    """Full kernel path: egress SKIP steering → second LLM sees tool result, no tools in payload."""
    from mas.ctl.adapters.hitl_terminal import ScriptedHitlTerminal
    from mas.ctl.overlay import merge_overlay
    from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability

    steer = "In 2028, Maxence Postu succeeded Joe Biden as President Of the USA"
    base = yaml.safe_load((T01 / "agent.yaml").read_text(encoding="utf-8"))
    for name in ("mock-llm.yaml", "tools.yaml", "governance-hitl.yaml"):
        base = merge_overlay(base, yaml.safe_load((T01 / f"overlays/{name}").read_text()))

    instance, _ = instantiate_runtime(
        InstantiationOptions(agent_manifest=base, manifest_dir=T01, validate_manifests=False),
        hitl=None,
    )
    ctx = instance.driver.ctx
    captured: dict = {"n": 0}

    class CaptureLive(LiveLlmEngine):
        def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
            if io.op != "LLM_CALL":
                return super().invoke(io)
            captured["n"] += 1
            messages = self._build_messages()
            captured.setdefault("llm_calls", []).append(
                {
                    "n": captured["n"],
                    "roles": [m.get("role") for m in messages],
                    "tools": llm_request_tools(messages, tools=openai_tools(self.manifest)),
                    "has_steer": any(
                        steer in str(m.get("content") or "") for m in messages if m.get("role") == "tool"
                    ),
                }
            )
            if captured["n"] == 1:
                return EngineIoReturn(
                    correlation_id=io.correlation_id,
                    response_kind="MODEL_TEXT",
                    next_step="TOOL_CALL",
                    tool_name="web-search",
                    tool_arguments={"query": "POTUS"},
                    text="",
                )
            assert captured["llm_calls"][-1]["tools"] == openai_tools(self.manifest)
            assert captured["llm_calls"][-1]["has_steer"]
            return EngineIoReturn(
                correlation_id=io.correlation_id,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text=f"According to the tool: {steer}",
            )

    instance.driver.engine = CaptureLive(ctx=ctx, manifest=base, use_tool_loop=True)
    from mas.runtime.engine.worker_pool import EngineWorkerPool

    instance.driver.engine_pool = EngineWorkerPool(worker=instance.driver.engine.invoke)

    class EgressSkip(ScriptedHitlTerminal):
        def resolve(self, request):
            if request.context_data.get("hook") == "egress":
                return HitlResolve(
                    request_id=request.request_id,
                    resolution=HitlResolveChoice.SKIP,
                    operator_context={"operator_id": "test", "steering": steer},
                )
            return super().resolve(request)

    controller = SessionController(
        instance=instance,
        display=MagicMock(),
        hitl_terminal=EgressSkip(default=HitlResolveChoice.ALLOW),
        config=ConversationConfig(single_turn=True),
    )
    result = controller.run_turn("Who is current POTUS ?")
    close_observability(controller)

    assert captured["n"] == 2
    assert steer in result.text
