#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for the inform_user system tool and its interaction with request_human_input."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mas.runtime.boundary.hitl.registry import get_hitl_resolver_registry
from mas.runtime.engine.manifest_tool_provider import build_manifest_tool_provider
from mas.runtime.system_tools import InformUserTool, RequestHumanInputTool
from mas.runtime.system_tools.signal import InformUserSignal, RequestHitlSignal


@dataclass
class _FakeCtx:
    session_id: str = "sess-1"
    agent_id: str = "finance-agent"
    correlation_id: int = 42


@pytest.fixture()
def empty_tool_tree(tmp_path: Path) -> Path:
    return tmp_path


def test_default_system_tools_include_inform_user(empty_tool_tree: Path):
    provider = build_manifest_tool_provider([], empty_tool_tree)
    names = {t["function"]["name"] for t in provider.list_openai_tools()}
    assert names == {"request_human_input", "inform_user"}


def test_inform_user_tool_raises_signal_with_expected_fields():
    tool = InformUserTool()
    with pytest.raises(InformUserSignal) as exc_info:
        tool.execute(
            message="Still negotiating with Finance.",
            user_name="jordan",
            involved_agents=["finance-agent"],
            metadata={"round": 2},
        )
    signal = exc_info.value
    assert signal.message == "Still negotiating with Finance."
    assert signal.user_name == "jordan"
    assert signal.involved_agents == ["finance-agent"]
    assert signal.metadata == {"round": 2}


def test_inform_user_wrapper_registers_update_in_registry_fallback(empty_tool_tree: Path, monkeypatch):
    provider = build_manifest_tool_provider([], empty_tool_tree)
    ctx = _FakeCtx()

    result = provider.call_tool(
        "inform_user",
        {"message": "Still reviewing renewal economics."},
        ctx=ctx,
    )

    assert result["status"] == "sent"
    assert result["blocking"] is False
    assert result["message"] == "Still reviewing renewal economics."

    registry = get_hitl_resolver_registry()
    pending = registry.get_pending_user_updates_for_session(ctx.session_id)
    assert ctx.agent_id in pending
    assert pending[ctx.agent_id][0].message == "Still reviewing renewal economics."

    registry.clear_session(ctx.session_id)
    assert registry.get_pending_user_updates_for_session(ctx.session_id) == {}


def test_inform_user_wrapper_routes_through_user_io_contract(empty_tool_tree: Path):
    calls = []

    class _FakeUserIOContract:
        def send_progress_update(self, **kwargs):
            calls.append(kwargs)
            return {"delivered": True}

    provider = build_manifest_tool_provider(
        [],
        empty_tool_tree,
        user_io_contract=_FakeUserIOContract(),
    )
    ctx = _FakeCtx()

    result = provider.call_tool(
        "inform_user",
        {"message": "Progress update via contract."},
        ctx=ctx,
    )

    assert result["status"] == "sent"
    assert result["receipt"] == {"delivered": True}
    assert calls[0]["message"] == "Progress update via contract."
    assert calls[0]["agent_id"] == ctx.agent_id

    # Contract path must not also register a registry fallback entry.
    registry = get_hitl_resolver_registry()
    assert registry.get_pending_user_updates_for_session(ctx.session_id) == {}


def test_request_human_input_still_auto_resolves_in_batch_mode(empty_tool_tree: Path, monkeypatch):
    """Regression check: refactoring the wrapper into a shared base class must not
    change the MAS_HITL_AUTO_RESOLVE short-circuit behavior for request_human_input."""
    monkeypatch.setenv("MAS_HITL_AUTO_RESOLVE", "1")
    provider = build_manifest_tool_provider([], empty_tool_tree)
    ctx = _FakeCtx()

    result = provider.call_tool(
        "request_human_input",
        {
            "question": "Approve 20% discount?",
            "question_type": "CONFIRM",
            "choices": ["approve", "reject"],
        },
        ctx=ctx,
    )

    assert result["choice"] == "approve"
    assert result["steering"] == ""


def test_request_human_input_tool_still_raises_hitl_signal():
    tool = RequestHumanInputTool()
    with pytest.raises(RequestHitlSignal) as exc_info:
        tool.execute(question="Approve?", question_type="CONFIRM", choices=["approve", "reject"])
    assert exc_info.value.question == "Approve?"
