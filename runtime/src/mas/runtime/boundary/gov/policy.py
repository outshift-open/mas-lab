#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Egress governance — parametric policy profiles aligned to TLA Governance.tla."""

from __future__ import annotations

from dataclasses import dataclass

from mas.runtime.schema.governance import (
    GovernanceAction,
    GovIngressProfile,
    GovPolicyProfile,
)


@dataclass(frozen=True)
class EgressIntentView:
    op: str
    destructive: bool
    correlation_id: int
    tool_name: str = ""
    tool_arguments: dict | None = None


def resolve_egress_governance(
    intent: EgressIntentView,
    *,
    profile: GovPolicyProfile,
    block_destructive: bool,
    policy_engine: object | None = None,
    hitl_gov_override: bool = False,
) -> GovernanceAction:
    if hitl_gov_override:
        return GovernanceAction.ALLOW
    if policy_engine is not None and intent.op == "TOOL_CALL" and intent.tool_name:
        from mas.runtime.boundary.gov.policy_engine import GovernancePolicyEngine

        assert isinstance(policy_engine, GovernancePolicyEngine)
        if policy_engine.is_blacklisted(intent.tool_name):
            return GovernanceAction.SKIP
        declarative = policy_engine.evaluate_trigger(
            "tool_input",
            {"arguments": intent.tool_arguments or {}},
            tool_name=intent.tool_name,
        )
        if declarative is not None:
            return declarative
    return egress_governance_outcome(
        intent,
        profile=profile,
        block_destructive=block_destructive,
    )


def egress_governance_outcome(
    intent: EgressIntentView,
    *,
    profile: GovPolicyProfile,
    block_destructive: bool,
) -> GovernanceAction:
    if profile == GovPolicyProfile.PERMISSIVE:
        return GovernanceAction.ALLOW
    if profile == GovPolicyProfile.BLOCK_DESTRUCTIVE:
        if intent.destructive and block_destructive:
            return GovernanceAction.BLOCK
        return GovernanceAction.ALLOW
    if profile == GovPolicyProfile.HITL_DESTRUCTIVE:
        if intent.destructive:
            return GovernanceAction.HITL
        return GovernanceAction.ALLOW
    if profile == GovPolicyProfile.LOG_ALL:
        return GovernanceAction.LOG
    if profile == GovPolicyProfile.MODIFY_DESTRUCTIVE:
        if intent.destructive:
            return GovernanceAction.MODIFY
        return GovernanceAction.ALLOW
    if profile == GovPolicyProfile.TERMINATE_DESTRUCTIVE:
        if intent.destructive:
            return GovernanceAction.TERMINATE
        return GovernanceAction.ALLOW
    if profile == GovPolicyProfile.SKIP_DESTRUCTIVE:
        if intent.destructive:
            return GovernanceAction.SKIP
        return GovernanceAction.ALLOW
    if profile == GovPolicyProfile.BLACKLIST_DESTRUCTIVE:
        if intent.destructive:
            return GovernanceAction.BLACKLIST
        return GovernanceAction.ALLOW
    if profile == GovPolicyProfile.RETRY_DESTRUCTIVE:
        if intent.destructive:
            return GovernanceAction.RETRY
        return GovernanceAction.ALLOW
    return GovernanceAction.ALLOW


def ingress_governance_outcome(
    *,
    response_kind: str,
    profile: GovIngressProfile,
) -> GovernanceAction:
    if profile == GovIngressProfile.PERMISSIVE:
        return GovernanceAction.ALLOW
    if response_kind != "ERROR":
        return GovernanceAction.ALLOW
    if profile == GovIngressProfile.RETRY_ON_ERROR:
        return GovernanceAction.RETRY
    if profile == GovIngressProfile.BLOCK_ON_ERROR:
        return GovernanceAction.BLOCK
    if profile == GovIngressProfile.SKIP_ON_ERROR:
        return GovernanceAction.SKIP
    return GovernanceAction.ALLOW


def apply_egress_modify(intent: EgressIntentView, action: GovernanceAction) -> EgressIntentView:
    if action == GovernanceAction.MODIFY and intent.destructive:
        return EgressIntentView(
            op=intent.op, destructive=False, correlation_id=intent.correlation_id
        )
    return intent
