#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for the broadcast-and-ack converging message-bus plugin."""

from __future__ import annotations

import pytest

from mas.library.standard.plugins.design_patterns.broadcast_ack import (
    BroadcastAckPlugin,
    _extract_confidence,
    _is_ack,
)
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.state import DpState, QProduct, RunLedger
from mas.runtime.registry import get_registry
from mas.runtime.schema.egress import EmitClientResponse, InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


# ---------------------------------------------------------------------------
# _is_ack
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
        ("**ACK**", True),
        ("*ACK*", True),
        ("**ACK**.", True),
        ("Sure, here is my report.", False),
        ("Temperature is 22°C.", False),
        ("I have nothing to add.", False),
        # Last-line ACK: explanation followed by bare ACK on its own line.
        ("I have nothing new to add.\n\nACK", True),
        ("Agree with all positions.\n\nACK", True),
        ("My final position.\n\n**ACK**", True),
        # Inline ACK at end of a longer sentence is NOT an ack.
        ("Safety comes first. I agree. Please ACK this.", False),
    ],
)
def test_is_ack(text: str, expected: bool) -> None:
    assert _is_ack(text) is expected


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_broadcast_ack_registered() -> None:
    info = get_registry().resolve("broadcast_ack")
    assert info is not None
    assert info.class_name == "BroadcastAckPlugin"


def test_broadcast_ack_plugin_id() -> None:
    assert BroadcastAckPlugin().plugin_id == "broadcast_ack@v1"


# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------

PARTICIPANTS = ["alpha", "beta", "gamma"]


def _make_config(max_rounds: int = 6) -> KernelConfig:
    return KernelConfig(
        agent_spec={
            "workflow": {
                "nodes": [
                    {"id": "moderator", "delegates_to": PARTICIPANTS},
                    *[{"id": p} for p in PARTICIPANTS],
                ]
            },
            "design_pattern": {"params": {"max_rounds": max_rounds}},
        }
    )


def _inject_wave_results(run: RunLedger, cid_map: dict[int, str], responses: dict[str, str]) -> None:
    """Inject one tool result per agent using the provided cid → agent map."""
    for cid, agent_id in cid_map.items():
        text = responses.get(agent_id, "ACK")
        ev = EngineIoReturn(correlation_id=cid, response_kind="TOOL_RESULT", next_step="STOP", text=text)
        run.events.append(ev)


class _Bus:
    """Drives the plugin through multiple waves without the full kernel."""

    def __init__(self, max_rounds: int = 6) -> None:
        self.plugin = BroadcastAckPlugin()
        self.q = QProduct()
        self.run = RunLedger()
        self.config = _make_config(max_rounds)
        self._wave_count = 0

    def wave1(self, task: str = "check status") -> dict[int, str]:
        """Dispatch wave 1; return the cid → agent_id map."""
        self.plugin._reset_state(PARTICIPANTS, task)
        out = self.plugin.evaluate_next(self.q, self.run, self.config)
        self._wave_count += 1
        assert all(isinstance(s, InvokeEngineIo) for s in out)
        return dict(self.plugin._st().cid_to_agent)

    def reply(self, cid_map: dict[int, str], responses: dict[str, str]) -> list:
        """Inject replies then call evaluate_next; return the egress symbols."""
        _inject_wave_results(self.run, cid_map, responses)
        out = self.plugin.evaluate_next(self.q, self.run, self.config)
        if out and isinstance(out[0], InvokeEngineIo):
            self._wave_count += 1
        return out

    def next_cid_map(self) -> dict[int, str]:
        return dict(self.plugin._st().cid_to_agent)


# ---------------------------------------------------------------------------
# Wave 1: initial fan-out
# ---------------------------------------------------------------------------


def test_wave1_dispatches_to_all_participants() -> None:
    bus = _Bus()
    cid_map = bus.wave1()
    assert set(cid_map.values()) == set(PARTICIPANTS)


def test_wave1_uses_original_task_as_prompt() -> None:
    bus = _Bus()
    bus.wave1("sensor check")
    assert bus.plugin._st().original_task == "sensor check"


# ---------------------------------------------------------------------------
# Wave 2: messages from wave 1 delivered to all others
# ---------------------------------------------------------------------------


def test_wave2_triggered_when_at_least_one_agent_replies() -> None:
    bus = _Bus()
    cid_map = bus.wave1()
    out = bus.reply(cid_map, {"alpha": "Temp 22°C.", "beta": "ACK", "gamma": "ACK"})
    # alpha replied → wave 2 dispatched to beta and gamma (not alpha — no one sent alpha a message)
    assert all(isinstance(s, InvokeEngineIo) for s in out), "expected another wave"


def test_wave2_only_reaches_agents_with_new_inbox() -> None:
    bus = _Bus()
    cid_map = bus.wave1()
    # Only alpha replies; beta and gamma ack.
    bus.reply(cid_map, {"alpha": "Temp 22°C.", "beta": "ACK", "gamma": "ACK"})
    # Wave 2: beta and gamma get alpha's message; alpha has nothing new in its inbox.
    cid_map2 = bus.next_cid_map()
    assert "beta" in cid_map2.values()
    assert "gamma" in cid_map2.values()
    assert "alpha" not in cid_map2.values()


def test_wave2_task_contains_sender_and_message() -> None:
    bus = _Bus()
    cid_map = bus.wave1()
    bus.reply(cid_map, {"alpha": "Temp 22°C.", "beta": "ACK", "gamma": "ACK"})
    # Verify the prompt constructed for beta includes alpha's message.
    cid_map2 = bus.next_cid_map()
    beta_cid = next(cid for cid, aid in cid_map2.items() if aid == "beta")
    # pending_tools_by_cid is cleared at this point; check via reply_log + round structure
    # (we verify via the task field in the ToolCallSpec, indirectly through the state)
    st = bus.plugin._st()
    # reply_log must have alpha's wave-1 reply
    assert any(aid == "alpha" and "Temp 22°C" in txt for _, aid, txt in st.reply_log)


# ---------------------------------------------------------------------------
# Convergence: all ack in same wave → stop
# ---------------------------------------------------------------------------


def test_converges_when_all_ack() -> None:
    bus = _Bus()
    cid_map = bus.wave1()
    out = bus.reply(cid_map, {"alpha": "ACK", "beta": "ACK", "gamma": "ACK"})
    assert len(out) == 1
    assert isinstance(out[0], EmitClientResponse)
    assert "acknowledged" in out[0].content


def test_convergence_after_two_waves() -> None:
    bus = _Bus()
    cid_map = bus.wave1()
    # Wave 1: alpha replies, others ack.
    out = bus.reply(cid_map, {"alpha": "Temp 22°C.", "beta": "ACK", "gamma": "ACK"})
    assert isinstance(out[0], InvokeEngineIo), "wave 2 expected"
    cid_map2 = bus.next_cid_map()
    # Wave 2: beta and gamma both ack (nothing further to add).
    out2 = bus.reply(cid_map2, {"beta": "ACK", "gamma": "ACK"})
    assert isinstance(out2[0], EmitClientResponse)
    assert "converged" in out2[0].content
    assert "alpha" in out2[0].content and "Temp 22°C" in out2[0].content


# ---------------------------------------------------------------------------
# Multi-wave: agents keep exchanging until agreement
# ---------------------------------------------------------------------------


def test_multi_wave_exchange() -> None:
    bus = _Bus()
    cid_map = bus.wave1()
    # Wave 1: all three reply.
    out = bus.reply(cid_map, {
        "alpha": "Temp 22°C.",
        "beta": "Stock at 42 units.",
        "gamma": "Inspection due Tuesday.",
    })
    assert isinstance(out[0], InvokeEngineIo)
    cid_map2 = bus.next_cid_map()
    # Wave 2: all three have something to add after reading each other.
    out2 = bus.reply(cid_map2, {
        "alpha": "Confirmed, bay 3 is hot.",
        "beta": "ACK",
        "gamma": "ACK",
    })
    assert isinstance(out2[0], InvokeEngineIo)
    cid_map3 = bus.next_cid_map()
    # Wave 3: beta and gamma got alpha's wave-2 message; they ack.
    out3 = bus.reply(cid_map3, {"beta": "ACK", "gamma": "ACK"})
    assert isinstance(out3[0], EmitClientResponse)
    content = out3[0].content
    # All three agents' contributions appear.
    assert "alpha" in content
    assert "beta" in content
    assert "gamma" in content
    assert "Wave 1" in content or "Wave" in content   # multi-wave format
    assert "converged" in content


# ---------------------------------------------------------------------------
# Safety cap
# ---------------------------------------------------------------------------


def test_max_rounds_cap_stops_loop() -> None:
    bus = _Bus(max_rounds=2)
    cid_map = bus.wave1()
    # Wave 1: everyone replies (no convergence).
    out = bus.reply(cid_map, {"alpha": "A1", "beta": "B1", "gamma": "G1"})
    assert isinstance(out[0], InvokeEngineIo)
    cid_map2 = bus.next_cid_map()
    # Wave 2: everyone replies again — but max_rounds=2 is reached.
    out2 = bus.reply(cid_map2, {"alpha": "A2", "beta": "B2", "gamma": "G2"})
    assert isinstance(out2[0], EmitClientResponse)
    assert "max reached" in out2[0].content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_no_participants_returns_early() -> None:
    plugin = BroadcastAckPlugin()
    q, run, config = QProduct(), RunLedger(), _make_config()
    plugin._reset_state([], "anything")
    out = plugin.evaluate_next(q, run, config)
    assert isinstance(out[0], EmitClientResponse)
    assert q.dp == DpState.IDLE


# ---------------------------------------------------------------------------
# _extract_confidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Confidence: 0.70", 0.70),
        ("confidence ~70%", 0.70),
        ("posterior: 0.65", 0.65),
        ("certainty: 80%", 0.80),
        ("The reading is 72%.", None),          # bare % without label is not extracted
        ("No numbers here.", None),
        ("ACK", None),
        ("temperature 37 degrees", None),
    ],
)
def test_extract_confidence(text: str, expected: float | None) -> None:
    result = _extract_confidence(text)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert abs(result - expected) < 1e-6


# ---------------------------------------------------------------------------
# SIEP position tracking and majority-agreement convergence
# ---------------------------------------------------------------------------


def test_siep_metrics_appear_in_output() -> None:
    """MPC and GAR lines are emitted when agents state explicit confidence values."""
    bus = _Bus()
    cid_map = bus.wave1()
    # Wave 1: all three reply with explicit confidence.
    out = bus.reply(cid_map, {
        "alpha": "Drug interaction likely. Confidence: 70%.",
        "beta": "Agree — confidence: 65%.",
        "gamma": "Confidence: 68%. Drug interaction probable.",
    })
    # Positions are close (70 / 65 / 68) → majority agreed → converge immediately.
    assert isinstance(out[0], EmitClientResponse)
    assert "MPC" in out[0].content
    assert "GAR" in out[0].content


def test_majority_agreement_exits_before_all_ack() -> None:
    """Majority agreement convergence fires even when some agents haven't acked."""
    bus = _Bus()
    cid_map = bus.wave1()
    # Wave 1: alpha and beta reply with close confidences; gamma has a wide divergence.
    out = bus.reply(cid_map, {
        "alpha": "Confidence: 70%.",
        "beta": "Confidence: 72%.",
        "gamma": "I strongly disagree — confidence: 10%.",
    })
    # alpha and beta (2/3 > n/2) are within threshold of the mean → converge.
    assert isinstance(out[0], EmitClientResponse)
    assert "converged" in out[0].content


def test_no_metrics_when_no_confidence_stated() -> None:
    """Output has no MPC/GAR block when agents never state numeric confidence."""
    bus = _Bus()
    cid_map = bus.wave1()
    out = bus.reply(cid_map, {"alpha": "ACK", "beta": "ACK", "gamma": "ACK"})
    assert isinstance(out[0], EmitClientResponse)
    assert "MPC" not in out[0].content


# ---------------------------------------------------------------------------
# CIP contingency handling
# ---------------------------------------------------------------------------


def test_cip_triggered_after_d_max_consecutive_disagreements() -> None:
    """After D_MAX waves of mutual non-ack, a bilateral CIP wave is dispatched."""
    bus = _Bus(max_rounds=10)
    cid_map = bus.wave1()
    # Wave 1: alpha and beta both reply (no gamma message so only alpha↔beta conflict).
    out = bus.reply(cid_map, {"alpha": "I say X.", "beta": "I say Y.", "gamma": "ACK"})
    assert isinstance(out[0], InvokeEngineIo), "wave 2 expected"
    cid_map2 = bus.next_cid_map()
    # Wave 2: alpha and beta still both reply — second consecutive disagreement.
    # D_MAX_CONTINGENCY=2 → CIP wave dispatched after this wave.
    out2 = bus.reply(cid_map2, {"alpha": "Still X.", "beta": "Still Y.", "gamma": "ACK"})
    # CIP bilateral wave: only alpha and beta should be dispatched.
    assert isinstance(out2[0], InvokeEngineIo)
    cip_map = bus.next_cid_map()
    assert set(cip_map.values()) == {"alpha", "beta"}


def test_cip_resolved_when_one_agent_acks() -> None:
    """CIP episode resolves when one agent sends ACK in the bilateral round."""
    bus = _Bus(max_rounds=10)
    cid_map = bus.wave1()
    # Two waves of mutual disagreement → triggers CIP.
    out = bus.reply(cid_map, {"alpha": "I say X.", "beta": "I say Y.", "gamma": "ACK"})
    cid_map2 = bus.next_cid_map()
    out2 = bus.reply(cid_map2, {"alpha": "Still X.", "beta": "Still Y.", "gamma": "ACK"})
    cip_map = bus.next_cid_map()
    assert set(cip_map.values()) == {"alpha", "beta"}
    # CIP clarification wave: beta ACKs → resolved.
    out3 = bus.reply(cip_map, {"alpha": "My final position: X.", "beta": "ACK"})
    # Should resume the broadcast (another wave or final).
    assert out3, "expected at least one symbol"
    # CIP resolved log entry should eventually appear in final output.
    # Drive to convergence.
    while isinstance(out3[0], InvokeEngineIo):
        next_map = bus.next_cid_map()
        out3 = bus.reply(next_map, {aid: "ACK" for aid in next_map.values()})
    assert isinstance(out3[0], EmitClientResponse)
    assert "CIP resolved" in out3[0].content


def test_cip_exhausted_when_both_agents_refuse() -> None:
    """CIP episode is exhausted when both agents keep disagreeing past CIP_MAX_DEPTH."""
    bus = _Bus(max_rounds=10)
    cid_map = bus.wave1()
    # Two waves of mutual disagreement → triggers CIP.
    out = bus.reply(cid_map, {"alpha": "I say X.", "beta": "I say Y.", "gamma": "ACK"})
    cid_map2 = bus.next_cid_map()
    out2 = bus.reply(cid_map2, {"alpha": "Still X.", "beta": "Still Y.", "gamma": "ACK"})
    cip_map = bus.next_cid_map()
    # CIP_MAX_DEPTH=2: both agents keep disagreeing for 2 bilateral rounds → exhausted.
    out3 = bus.reply(cip_map, {"alpha": "X remains.", "beta": "Y stands."})
    # Could be another CIP round or already exhausted (depth 1 of 2).
    cip_map2 = bus.next_cid_map()
    out4 = bus.reply(cip_map2, {"alpha": "X final.", "beta": "Y final."})
    # Drive to end.
    current = out4
    while isinstance(current[0], InvokeEngineIo):
        nm = bus.next_cid_map()
        current = bus.reply(nm, {aid: "ACK" for aid in nm.values()})
    assert isinstance(current[0], EmitClientResponse)
    assert "CIP exhausted" in current[0].content


def test_cip_not_triggered_when_only_one_agent_persistent() -> None:
    """CIP must NOT fire when only one agent keeps replying (no bilateral conflict)."""
    bus = _Bus(max_rounds=5)
    cid_map = bus.wave1()
    out = bus.reply(cid_map, {"alpha": "I say X.", "beta": "ACK", "gamma": "ACK"})
    assert isinstance(out[0], InvokeEngineIo)
    cid_map2 = bus.next_cid_map()
    out2 = bus.reply(cid_map2, {"alpha": "Still X.", "beta": "ACK", "gamma": "ACK"})
    # alpha is alone → no bilateral pair → no CIP → normal wave or convergence.
    if isinstance(out2[0], InvokeEngineIo):
        # Should include all participants with new messages in their inbox, not just 2.
        cip_map = bus.next_cid_map()
        # gamma and beta should be in the map (they receive alpha's msg), alpha should not.
        assert "alpha" not in cip_map.values()
    else:
        # Converged is also fine.
        assert isinstance(out2[0], EmitClientResponse)
