#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for the broadcast-and-ack design-pattern plugin."""

from __future__ import annotations

import pytest

from mas.library.standard.plugins.design_patterns.broadcast_ack import (
    BroadcastAckPlugin,
    _is_ack,
)
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.state import DpState, QProduct, RunLedger
from mas.runtime.registry import get_registry
from mas.runtime.schema.egress import EmitClientResponse, InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


# ---------------------------------------------------------------------------
# _is_ack helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", True),
        ("   ", True),
        ("ACK", True),
        ("ack", True),
        ("Ack received.", True),
        ("ACK: message received", True),
        ("Sure, here is my report.", False),
        ("Temperature is 22°C.", False),
        ("I have nothing to add.", False),
    ],
)
def test_is_ack(text: str, expected: bool) -> None:
    assert _is_ack(text) is expected


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def test_broadcast_ack_registered_in_registry() -> None:
    info = get_registry().resolve("broadcast_ack")
    assert info is not None
    assert info.class_name == "BroadcastAckPlugin"


def test_broadcast_ack_plugin_id() -> None:
    plugin = BroadcastAckPlugin()
    assert plugin.plugin_id == "broadcast_ack@v1"


# ---------------------------------------------------------------------------
# evaluate_next — fan-out round
# ---------------------------------------------------------------------------

def _make_config(participants: list[str]) -> KernelConfig:
    return KernelConfig(
        agent_spec={
            "workflow": {
                "nodes": [
                    {"id": "moderator", "delegates_to": participants},
                    *[{"id": p} for p in participants],
                ]
            }
        }
    )


def test_evaluate_next_first_call_fans_out_in_parallel() -> None:
    plugin = BroadcastAckPlugin()
    q = QProduct()
    run = RunLedger()
    config = _make_config(["alpha", "beta", "gamma"])

    plugin._reset_state(["alpha", "beta", "gamma"], "check status")
    out = plugin.evaluate_next(q, run, config=config)

    # Must emit parallel tool-call egress for all three peers.
    assert len(out) == 3
    assert all(isinstance(sym, InvokeEngineIo) and sym.op == "TOOL_CALL" for sym in out)
    tool_names = {q.pending_tools_by_cid[sym.correlation_id][0] for sym in out}
    assert tool_names == {"delegate_to_alpha", "delegate_to_beta", "delegate_to_gamma"}


# ---------------------------------------------------------------------------
# evaluate_next — result aggregation
# ---------------------------------------------------------------------------

def _inject_tool_results(run: RunLedger, results: list[str]) -> None:
    for i, text in enumerate(results, start=1):
        event = EngineIoReturn(correlation_id=i, response_kind="TOOL_RESULT", next_step="STOP", text=text)
        run.events.append(event)


def test_evaluate_next_aggregates_replies_and_counts_acks() -> None:
    plugin = BroadcastAckPlugin()
    q = QProduct()
    run = RunLedger()
    config = _make_config(["alpha", "beta", "gamma"])

    plugin._reset_state(["alpha", "beta", "gamma"], "check status")
    plugin._state().next_idx = 1  # simulate that fan-out already happened

    _inject_tool_results(run, [
        "Temperature is 22°C and humidity is 58%.",  # reply
        "ACK",                                        # bare ack
        "Stock levels nominal; 42 units in bay 3.",  # reply
    ])

    out = plugin.evaluate_next(q, run, config=config)

    assert len(out) == 1
    result = out[0]
    assert isinstance(result, EmitClientResponse)
    assert result.finish_reason == "stop"
    assert "Reply 1" in result.content
    assert "Reply 2" in result.content
    assert "1 peer(s) acknowledged without reply" in result.content
    assert q.dp == DpState.IDLE


def test_evaluate_next_all_acks_produces_ack_only_summary() -> None:
    plugin = BroadcastAckPlugin()
    q = QProduct()
    run = RunLedger()
    config = _make_config(["alpha", "beta"])

    plugin._reset_state(["alpha", "beta"], "ping")
    plugin._state().next_idx = 1

    _inject_tool_results(run, ["ACK", ""])

    out = plugin.evaluate_next(q, run, config=config)

    assert isinstance(out[0], EmitClientResponse)
    assert "Broadcast acknowledged by all peers" in out[0].content
    assert q.dp == DpState.IDLE


def test_evaluate_next_no_participants_returns_early() -> None:
    plugin = BroadcastAckPlugin()
    q = QProduct()
    run = RunLedger()
    config = _make_config([])

    plugin._reset_state([], "anything")
    out = plugin.evaluate_next(q, run, config=config)

    assert isinstance(out[0], EmitClientResponse)
    assert q.dp == DpState.IDLE


def test_evaluate_next_all_replies_no_ack_note() -> None:
    plugin = BroadcastAckPlugin()
    q = QProduct()
    run = RunLedger()
    config = _make_config(["alpha", "beta"])

    plugin._reset_state(["alpha", "beta"], "report please")
    plugin._state().next_idx = 1

    _inject_tool_results(run, ["All systems green.", "Battery at 95%."])

    out = plugin.evaluate_next(q, run, config=config)

    assert isinstance(out[0], EmitClientResponse)
    # No ack count line when every peer replied.
    assert "acknowledged without reply" not in out[0].content
    assert "Reply 1" in out[0].content
    assert "Reply 2" in out[0].content
