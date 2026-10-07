#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance-block handlers — policy, HITL, budget, and control events.

Every governance event maps to a ``GovernanceEvent`` point span carrying the
governance kind, outcome, and policy identifiers.  Governance is an opt-in
export layer (``ExportLayers.governance``).

Ontology block: ``governance`` (governance summand).
"""

from __future__ import annotations

from typing import Any, Dict

from mas.library.telemetry.conversion.mappings.base import SpanEmitter, register


@register("governance_event", "governance_checked")
def h_governance_event(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    conv.point_span(
        "GovernanceEvent",
        {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": conv.agent_id(ev),
            "mas.governance.kind": ev.get("kind", "governance_checked"),
            "mas.governance.hook": ev.get("hook", ""),
            "mas.governance.outcome": ev.get("outcome", "allowed"),
            "mas.governance.checks_passed": int(ev.get("checks_passed") or 0),
        },
        ev.get("parent_call_id"),
        ts_ns=conv.ts_ns(ev),
    )


@register("governance_policy", "transformation_event")
def h_governance_policy(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    attrs: Dict[str, Any] = {
        "mas.boundary": "GovernanceEvent",
        "mas.agent.id": conv.agent_id(ev),
        "mas.governance.kind": ev.get("kind", "governance_policy"),
        "mas.governance.policy_name": ev.get("policy_name", ""),
        "mas.governance.trigger_point": ev.get("trigger_point", ""),
        "mas.governance.evaluation_mode": ev.get("evaluation_mode", ""),
        "mas.governance.outcome": ev.get("outcome", ""),
        "mas.governance.action_taken": ev.get("action_taken", ""),
    }
    details = ev.get("details") or {}
    if details.get("condition"):
        attrs["mas.governance.condition"] = details["condition"]
    if details.get("tool_filter"):
        attrs["mas.governance.tool_filter"] = details["tool_filter"]
    conv.point_span(
        "GovernanceEvent", attrs, ev.get("parent_call_id"), ts_ns=conv.ts_ns(ev)
    )


@register("hitl_request")
def h_hitl_request(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    conv.point_span(
        "GovernanceEvent",
        {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": conv.agent_id(ev),
            "mas.governance.kind": ev.get("kind", "hitl_request"),
            "mas.governance.policy_name": ev.get("policy_name", ""),
            "mas.governance.auto_approve": ev.get("auto_approve", False),
            "mas.governance.timeout_s": ev.get("timeout_s", 30.0),
        },
        ev.get("parent_call_id"),
        ts_ns=conv.ts_ns(ev),
    )


@register("policy_denial", "policy_allow")
def h_policy_event(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    conv.point_span(
        "GovernanceEvent",
        {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": conv.agent_id(ev),
            "mas.governance.kind": ev.get("kind", "policy_denial"),
            "mas.governance.decision_type": ev.get("decision_type", "deny"),
            "mas.governance.policy_id": ev.get("policy_id", ""),
            "mas.governance.reason": ev.get("reason", ""),
            "mas.governance.denied_call_id": ev.get("denied_call_id", ""),
        },
        ev.get("parent_call_id"),
        ts_ns=conv.ts_ns(ev),
    )


@register("hitl_gate")
def h_hitl_gate(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    _decision_event(conv, ev, "hitl_gate")


@register("budget_event")
def h_budget_event(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    _decision_event(conv, ev, "budget_event")


@register("control_intervention")
def h_control_intervention(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    _decision_event(conv, ev, "control_intervention")


def _decision_event(conv: SpanEmitter, ev: Dict[str, Any], default_kind: str) -> None:
    conv.point_span(
        "GovernanceEvent",
        {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": conv.agent_id(ev),
            "mas.governance.kind": ev.get("kind", default_kind),
            "mas.governance.decision_type": ev.get("decision_type", ""),
            "mas.governance.policy_id": ev.get("policy_id", ""),
            "mas.governance.reason": ev.get("reason", ""),
        },
        ev.get("parent_call_id"),
        ts_ns=conv.ts_ns(ev),
    )


@register("governance_denied")
def h_governance_denied(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    conv.point_span(
        "GovernanceEvent",
        {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": conv.agent_id(ev),
            "mas.governance.kind": ev.get("kind", "governance_denied"),
            "mas.governance.decision_type": "deny",
            "mas.governance.policy_id": ev.get("contract_id")
            or ev.get("policy_id", ""),
            "mas.governance.hook": ev.get("hook", ""),
            "mas.governance.reason": str(ev.get("reason", ""))[:500],
        },
        ev.get("parent_call_id"),
        ts_ns=conv.ts_ns(ev),
    )


@register("governance_decision")
def h_governance_decision(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    _decision_event(conv, ev, "governance_decision")


@register(
    "governance_authorize_start",
    "governance_validate_start",
    "obs_wrap_gov_authorize_start",
    "obs_wrap_gov_validate_start",
    "checkpoint_start",
)
def h_governance_interval_start(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    conv.open_span(
        conv.span_key(ev),
        "GovernanceEvent",
        {
            "mas.boundary": "GovernanceEvent",
            "mas.agent.id": conv.agent_id(ev),
            "mas.governance.kind": ev.get("kind", "governance"),
            "mas.governance.hook": ev.get("hook", ""),
            "mas.governance.outcome": ev.get("outcome", ""),
        },
        ev.get("parent_call_id"),
        start_ns=conv.ts_ns(ev),
    )


@register(
    "governance_authorize_end",
    "governance_validate_end",
    "obs_wrap_gov_authorize_end",
    "obs_wrap_gov_validate_end",
    "checkpoint_end",
)
def h_governance_interval_end(conv: SpanEmitter, ev: Dict[str, Any]) -> None:
    conv.close_span(
        conv.span_key(ev),
        status=ev.get("status", "success"),
        end_ns=conv.ts_ns(ev),
    )
