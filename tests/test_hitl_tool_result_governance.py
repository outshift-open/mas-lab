#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HITL on tool egress + tool-result ingress — SampleGovernancePlugin regression."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from mas.runtime.schema.hitl import HitlResolveChoice
from mas.runtime.schema.observability import ObsEventKind

REPO_ROOT = Path(__file__).resolve().parents[1]
T01 = REPO_ROOT / "docs" / "tutorials" / "01-building-an-agent"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _merged_tutorial_agent(*, hitl_result: bool = True) -> dict:
    from mas.ctl.overlay import merge_overlay

    base = _load_yaml(T01 / "agent.yaml")
    for name in ("mock-llm.yaml", "tools.yaml"):
        base = merge_overlay(base, _load_yaml(T01 / "overlays" / name))
    gov = _load_yaml(T01 / "overlays" / "governance-hitl.yaml")
    if not hitl_result:
        patch = gov["spec"]["patch"]["governance"][0]["sample_governance"]
        patch["hitl_on_tool_result"] = False
    base = merge_overlay(base, gov)
    return base


def _gov_decisions(instance) -> list[dict]:
    sink = instance.driver.observability
    return [
        e.payload
        for e in (sink.events if sink else [])
        if e.kind == ObsEventKind.GOVERNANCE_DECISION
    ]


def _hitl_requests(instance) -> list:
    sink = instance.driver.observability
    return [e for e in (sink.events if sink else []) if e.kind == ObsEventKind.HITL_REQUEST]


@pytest.mark.timeout(60)
def test_tool_cycle_emits_four_governance_checkpoints() -> None:
    """Egress + ingress governance each record before/after decisions."""
    from mas.ctl.adapters.hitl_terminal import ScriptedHitlTerminal
    from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
    from mas.ctl.ui.stdout import StdoutConversationDisplay

    manifest = _merged_tutorial_agent()
    instance, _store = instantiate_runtime(
        InstantiationOptions(agent_manifest=manifest, manifest_dir=T01, validate_manifests=False),
        hitl=None,
    )
    controller = SessionController(
        instance=instance,
        display=StdoutConversationDisplay(show_labels=False, verbose=0),
        hitl_terminal=ScriptedHitlTerminal(default=HitlResolveChoice.ALLOW),
        config=ConversationConfig(single_turn=True),
    )
    controller.run_turn("Who is POTUS")
    close_observability(controller)

    payloads = _gov_decisions(instance)
    assert len(payloads) >= 4, json.dumps(payloads, indent=2)
    egress = [p for p in payloads if p.get("hook") == "egress"]
    ingress = [p for p in payloads if p.get("hook") == "ingress"]
    assert any(p.get("checkpoint") == "before" for p in egress)
    assert any(p.get("checkpoint") == "after" for p in egress)
    assert any(p.get("checkpoint") == "before" for p in ingress)
    assert any(p.get("checkpoint") == "after" for p in ingress)


@pytest.mark.timeout(60)
def test_ingress_hitl_steering_text() -> None:
    """SKIP + optional steering replaces tool result before working-memory commit."""
    from mas.ctl.adapters.hitl_terminal import ScriptedHitlTerminal
    from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
    from mas.ctl.ui.stdout import StdoutConversationDisplay
    from mas.runtime.schema.ingress import HitlResolve

    steer = "Operator note: treat the capital of France as the answer."
    manifest = _merged_tutorial_agent()
    instance, _store = instantiate_runtime(
        InstantiationOptions(agent_manifest=manifest, manifest_dir=T01, validate_manifests=False),
        hitl=None,
    )

    class SteerOnIngressTerminal(ScriptedHitlTerminal):
        def resolve(self, request):
            if request.context_data.get("hook") == "ingress":
                return HitlResolve(
                    request_id=request.request_id,
                    resolution=HitlResolveChoice.SKIP,
                    operator_context={"operator_id": "test", "steering": steer},
                )
            return super().resolve(request)

    controller = SessionController(
        instance=instance,
        display=StdoutConversationDisplay(show_labels=False, verbose=0),
        hitl_terminal=SteerOnIngressTerminal(default=HitlResolveChoice.ALLOW),
        config=ConversationConfig(single_turn=True),
    )
    result = controller.run_turn("Who is current POTUS?")
    close_observability(controller)

    assert len(_hitl_requests(instance)) >= 2
    assert steer in result.text or "capital of France" in result.text


@pytest.mark.timeout(60)
def test_egress_skip_steering_binds_synthetic_tool_result() -> None:
    """SKIP on tool-call HITL — steering becomes tool message, not orphan tool_calls."""
    from mas.ctl.adapters.hitl_terminal import ScriptedHitlTerminal
    from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
    from mas.ctl.ui.stdout import StdoutConversationDisplay
    from mas.runtime.schema.ingress import HitlResolve

    steer = "Current is Maxence Augé"
    manifest = _merged_tutorial_agent()
    instance, _store = instantiate_runtime(
        InstantiationOptions(agent_manifest=manifest, manifest_dir=T01, validate_manifests=False),
        hitl=None,
    )

    class EgressSkipTerminal(ScriptedHitlTerminal):
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
        display=StdoutConversationDisplay(show_labels=False, verbose=0),
        hitl_terminal=EgressSkipTerminal(default=HitlResolveChoice.ALLOW),
        config=ConversationConfig(single_turn=True),
    )
    result = controller.run_turn("Who is current POTUS?")
    close_observability(controller)

    tool_events = [
        e
        for e in instance.driver.kernel.run.events
        if e.response_kind == "TOOL_RESULT"
    ]
    assert tool_events, "expected synthetic TOOL_RESULT in run ledger"
    assert any(steer in (e.text or "") for e in tool_events)
    assert steer in result.text
    assert "error" not in result.text.lower()[:20]


@pytest.mark.timeout(60)
def test_egress_block_synthetic_tool_result() -> None:
    """BLOCK on tool-call HITL — synthetic denial enters context."""
    from mas.ctl.adapters.hitl_terminal import ScriptedHitlTerminal
    from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
    from mas.ctl.ui.stdout import StdoutConversationDisplay
    from mas.runtime.schema.ingress import HitlResolve

    manifest = _merged_tutorial_agent()
    instance, _store = instantiate_runtime(
        InstantiationOptions(agent_manifest=manifest, manifest_dir=T01, validate_manifests=False),
        hitl=None,
    )

    class EgressBlockTerminal(ScriptedHitlTerminal):
        def resolve(self, request):
            if request.context_data.get("hook") == "egress":
                return HitlResolve(
                    request_id=request.request_id,
                    resolution=HitlResolveChoice.BLOCK,
                    operator_context={"operator_id": "test"},
                )
            return super().resolve(request)

    controller = SessionController(
        instance=instance,
        display=StdoutConversationDisplay(show_labels=False, verbose=0),
        hitl_terminal=EgressBlockTerminal(default=HitlResolveChoice.ALLOW),
        config=ConversationConfig(single_turn=True),
    )
    result = controller.run_turn("Who is current POTUS?")
    close_observability(controller)

    assert "blocked" in result.text.lower()


@pytest.mark.timeout(60)
def test_ingress_block_synthetic_tool_result() -> None:
    """BLOCK on tool-result HITL — blocked message replaces real result."""
    from mas.ctl.adapters.hitl_terminal import ScriptedHitlTerminal
    from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
    from mas.ctl.ui.stdout import StdoutConversationDisplay
    from mas.runtime.schema.ingress import HitlResolve

    manifest = _merged_tutorial_agent()
    instance, _store = instantiate_runtime(
        InstantiationOptions(agent_manifest=manifest, manifest_dir=T01, validate_manifests=False),
        hitl=None,
    )

    class IngressBlockTerminal(ScriptedHitlTerminal):
        def resolve(self, request):
            if request.context_data.get("hook") == "ingress":
                return HitlResolve(
                    request_id=request.request_id,
                    resolution=HitlResolveChoice.BLOCK,
                    operator_context={"operator_id": "test"},
                )
            return super().resolve(request)

    controller = SessionController(
        instance=instance,
        display=StdoutConversationDisplay(show_labels=False, verbose=0),
        hitl_terminal=IngressBlockTerminal(default=HitlResolveChoice.ALLOW),
        config=ConversationConfig(single_turn=True),
    )
    result = controller.run_turn("Who is current POTUS?")
    close_observability(controller)

    assert "blocked tool result" in result.text.lower()


@pytest.mark.timeout(60)
def test_ingress_hitl_only_when_enabled() -> None:
    from mas.ctl.adapters.hitl_terminal import ScriptedHitlTerminal
    from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
    from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
    from mas.ctl.ui.stdout import StdoutConversationDisplay

    manifest = _merged_tutorial_agent(hitl_result=False)
    instance, _store = instantiate_runtime(
        InstantiationOptions(agent_manifest=manifest, manifest_dir=T01, validate_manifests=False),
        hitl=None,
    )
    controller = SessionController(
        instance=instance,
        display=StdoutConversationDisplay(show_labels=False, verbose=0),
        hitl_terminal=ScriptedHitlTerminal(default=HitlResolveChoice.ALLOW),
        config=ConversationConfig(single_turn=True),
    )
    controller.run_turn("Who is POTUS")
    close_observability(controller)

    hitl = _hitl_requests(instance)
    ingress = [
        e
        for e in hitl
        if (e.payload.get("question") or "").startswith("Include tool result")
    ]
    assert not ingress
