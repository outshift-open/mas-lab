#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for request_human_input's configurable timeout and auto-resolve decision."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from mas.runtime.boundary.hitl.registry import get_hitl_resolver_registry
from mas.runtime.engine.manifest_tool_provider import build_manifest_tool_provider
from mas.runtime.system_tools.request_human_input import RequestHumanInputTool


@dataclass
class _FakeCtx:
    session_id: str
    agent_id: str = "finance-agent"
    correlation_id: int = 1


@pytest.fixture()
def empty_tool_tree(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_hitl_env(monkeypatch):
    """MAS_HITL_AUTO_RESOLVE is set via os.environ.setdefault (not monkeypatch)
    by benchmark/batch-run code elsewhere, so it can leak into this file's
    tests when the whole suite runs in one process (e.g. after
    tests/test_golden_labs_run.py). Guarantee a clean baseline here; tests
    that actually want auto-resolve set it themselves via monkeypatch."""
    monkeypatch.delenv("MAS_HITL_AUTO_RESOLVE", raising=False)
    monkeypatch.delenv("MAS_HITL_AUTO_RESOLVE_DECISION", raising=False)


# ---------------------------------------------------------------------------
# timeout: default None (block until resolved, no TimeoutError), configurable
# per call and via the manifest's spec.tools system-tool entry
# ---------------------------------------------------------------------------

def test_input_schema_defaults_timeout_to_none():
    """No timeout argument -> RequestHitlSignal.timeout is None (block forever)."""
    from mas.runtime.system_tools.signal import RequestHitlSignal

    tool = RequestHumanInputTool()
    with pytest.raises(RequestHitlSignal) as exc_info:
        tool.execute(question="Approve?", question_type="CONFIRM", choices=["approve", "reject"])
    assert exc_info.value.timeout is None


def test_default_wrapper_has_no_timeout_when_nothing_configured(empty_tool_tree: Path):
    provider = build_manifest_tool_provider([], empty_tool_tree)
    wrapper = next(
        t for t in provider._tool_instances if getattr(t, "_tool", None).__class__.__name__ == "RequestHumanInputTool"
    )
    assert wrapper._default_timeout_seconds is None


def test_manifest_params_set_the_default_timeout(empty_tool_tree: Path):
    provider = build_manifest_tool_provider(
        [{"kind": "system", "name": "request_human_input", "params": {"timeout": 5}}],
        empty_tool_tree,
    )
    wrapper = next(
        t for t in provider._tool_instances if getattr(t, "_tool", None).__class__.__name__ == "RequestHumanInputTool"
    )
    assert wrapper._default_timeout_seconds == 5


def test_no_timeout_configured_blocks_until_resolved(empty_tool_tree: Path):
    """With neither a manifest default nor a call-time timeout, the wrapper
    must wait indefinitely for resolution -- not silently apply some other
    default. Resolved promptly from another thread here so the test itself
    doesn't hang."""
    provider = build_manifest_tool_provider([], empty_tool_tree)
    ctx = _FakeCtx(session_id="sess-block")
    registry = get_hitl_resolver_registry()
    result: dict = {}

    def resolve_soon():
        # Give on_execute_tool a moment to register before resolving.
        for _ in range(50):
            if registry.has_pending(ctx.session_id, ctx.agent_id):
                break
            time.sleep(0.01)
        registry.resolve(ctx.session_id, ctx.agent_id, ctx.correlation_id, choice="approve", steering="")

    threading.Thread(target=resolve_soon, daemon=True).start()

    result["value"] = provider.call_tool(
        "request_human_input",
        {"question": "Approve?", "question_type": "CONFIRM", "choices": ["approve", "reject"]},
        ctx=ctx,
    )
    assert result["value"]["choice"] == "approve"


def test_call_time_timeout_raises_after_configured_seconds(empty_tool_tree: Path):
    provider = build_manifest_tool_provider([], empty_tool_tree)
    ctx = _FakeCtx(session_id="sess-timeout")

    with pytest.raises(TimeoutError):
        provider.call_tool(
            "request_human_input",
            {
                "question": "Approve?",
                "question_type": "CONFIRM",
                "choices": ["approve", "reject"],
                "timeout": 0.05,
            },
            ctx=ctx,
        )


def test_call_time_timeout_overrides_manifest_default(empty_tool_tree: Path):
    """A longer manifest default must not stop a call from asking for a
    shorter timeout for that one request."""
    provider = build_manifest_tool_provider(
        [{"kind": "system", "name": "request_human_input", "params": {"timeout": 60}}],
        empty_tool_tree,
    )
    ctx = _FakeCtx(session_id="sess-override")

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        provider.call_tool(
            "request_human_input",
            {
                "question": "Approve?",
                "question_type": "CONFIRM",
                "choices": ["approve", "reject"],
                "timeout": 0.05,
            },
            ctx=ctx,
        )
    assert time.monotonic() - start < 5


# ---------------------------------------------------------------------------
# auto-resolve decision: defaults to "approve", configurable
# ---------------------------------------------------------------------------

def test_auto_resolve_defaults_to_approve(empty_tool_tree: Path, monkeypatch):
    monkeypatch.setenv("MAS_HITL_AUTO_RESOLVE", "1")
    provider = build_manifest_tool_provider([], empty_tool_tree)
    ctx = _FakeCtx(session_id="sess-auto-default")

    result = provider.call_tool(
        "request_human_input",
        {"question": "Approve?", "question_type": "CONFIRM", "choices": ["approve", "reject"]},
        ctx=ctx,
    )
    assert result["choice"] == "approve"


def test_auto_resolve_decision_configurable_via_env_var(empty_tool_tree: Path, monkeypatch):
    monkeypatch.setenv("MAS_HITL_AUTO_RESOLVE", "1")
    monkeypatch.setenv("MAS_HITL_AUTO_RESOLVE_DECISION", "reject")
    provider = build_manifest_tool_provider([], empty_tool_tree)
    ctx = _FakeCtx(session_id="sess-auto-env")

    result = provider.call_tool(
        "request_human_input",
        {"question": "Approve?", "question_type": "CONFIRM", "choices": ["approve", "reject"]},
        ctx=ctx,
    )
    assert result["choice"] == "reject"


def test_auto_resolve_decision_configurable_via_manifest_params(empty_tool_tree: Path, monkeypatch):
    monkeypatch.setenv("MAS_HITL_AUTO_RESOLVE", "1")
    provider = build_manifest_tool_provider(
        [{"kind": "system", "name": "request_human_input", "params": {"auto_resolve_decision": "reject"}}],
        empty_tool_tree,
    )
    ctx = _FakeCtx(session_id="sess-auto-manifest")

    result = provider.call_tool(
        "request_human_input",
        {"question": "Approve?", "question_type": "CONFIRM", "choices": ["approve", "reject"]},
        ctx=ctx,
    )
    assert result["choice"] == "reject"


def test_manifest_auto_resolve_decision_wins_over_env_var(empty_tool_tree: Path, monkeypatch):
    monkeypatch.setenv("MAS_HITL_AUTO_RESOLVE", "1")
    monkeypatch.setenv("MAS_HITL_AUTO_RESOLVE_DECISION", "reject")
    provider = build_manifest_tool_provider(
        [{"kind": "system", "name": "request_human_input", "params": {"auto_resolve_decision": "escalate"}}],
        empty_tool_tree,
    )
    ctx = _FakeCtx(session_id="sess-auto-precedence")

    result = provider.call_tool(
        "request_human_input",
        {"question": "Approve?", "question_type": "CONFIRM", "choices": ["approve", "reject", "escalate"]},
        ctx=ctx,
    )
    assert result["choice"] == "escalate"
