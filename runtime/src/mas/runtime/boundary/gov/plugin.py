#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance plugin contract — M_gov asks; plugin replies; Mealy applies coupling."""

from __future__ import annotations

from typing import Protocol

from mas.runtime.boundary.gov.policy import EgressIntentView, resolve_egress_governance
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import GovDecision


class GovernancePlugin(Protocol):
    """Evaluate egress at chokepoint (policy/HITL rules live in plugins, not in M_tool/M_dp)."""

    def evaluate_egress(self, intent: EgressIntentView, *, config: KernelConfig) -> GovDecision: ...


class KernelGovernancePlugin:
    """Default plugin — wraps parametric policy profiles + declarative policy engine."""

    def evaluate_egress(self, intent: EgressIntentView, *, config: KernelConfig) -> GovDecision:
        if config.hitl_on_tool and intent.op == "TOOL_CALL":
            return GovDecision.HITL
        action = resolve_egress_governance(
            intent,
            profile=config.gov_policy_profile,
            block_destructive=config.gov_block_destructive,
            policy_engine=config.policy_engine,
            hitl_gov_override=False,
        )
        return GovDecision(action.value)


def evaluate_egress_at_chokepoint(
    intent: EgressIntentView,
    *,
    config: KernelConfig,
    plugin: GovernancePlugin | None = None,
    hitl_gov_override: bool = False,
) -> GovDecision:
    if hitl_gov_override:
        return GovDecision.ALLOW
    impl = plugin or getattr(config, "egress_governance_plugin", None) or KernelGovernancePlugin()
    return impl.evaluate_egress(intent, config=config)
