#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance plugin contract — M_gov asks; plugin replies; Mealy applies coupling."""

from __future__ import annotations

from typing import Protocol

from mas.runtime.boundary.gov.policy import EgressIntentView, resolve_egress_governance
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import GovDecision

# (decision, policy_name, human-readable reason) — computed together so the
# reason can never describe a different decision than the one returned
# alongside it. See boundary/gov/policy.py's module docstring for why this
# replaced a separate after-the-fact reconstruction.
EgressDecision = tuple[GovDecision, str, str]


class GovernancePlugin(Protocol):
    """Evaluate egress at chokepoint (policy/HITL rules live in plugins, not in M_tool/M_dp)."""

    def evaluate_egress(self, intent: EgressIntentView, *, config: KernelConfig) -> EgressDecision: ...


class KernelGovernancePlugin:
    """Default plugin — wraps parametric policy profiles + declarative policy engine."""

    def evaluate_egress(self, intent: EgressIntentView, *, config: KernelConfig) -> EgressDecision:
        if config.hitl_on_tool and intent.op == "TOOL_CALL":
            return (
                GovDecision.HITL,
                "hitl-on-tool",
                "the hitl_on_tool flag requires human review for every tool call",
            )
        action, policy_name, reason = resolve_egress_governance(
            intent,
            profile=config.gov_policy_profile,
            block_destructive=config.gov_block_destructive,
            policy_engine=config.policy_engine,
        )
        return GovDecision(action.value), policy_name, reason


def evaluate_egress_at_chokepoint(
    intent: EgressIntentView,
    *,
    config: KernelConfig,
    plugin: GovernancePlugin | None = None,
    hitl_gov_override: bool = False,
) -> EgressDecision:
    """Return the ``(decision, policy_name, reason)`` egress verdict for one
    call. A prior human approval (``hitl_gov_override``) short-circuits to
    ALLOW before ``plugin`` (or ``config.egress_governance_plugin``, or the
    default ``KernelGovernancePlugin``) is ever consulted."""
    if hitl_gov_override:
        return GovDecision.ALLOW, "hitl-override", "a prior human approval covers this call"
    impl = plugin or getattr(config, "egress_governance_plugin", None) or KernelGovernancePlugin()
    return impl.evaluate_egress(intent, config=config)
