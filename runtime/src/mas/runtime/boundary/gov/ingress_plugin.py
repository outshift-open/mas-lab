#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress governance plugins — classify engine signals; kernel applies decisions (no recovery arcs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from mas.runtime.boundary.gov.error_recovery import (
    ErrorRecoveryPlugin,
    map_recovery_to_governance,
)
from mas.runtime.boundary.gov.policy import ingress_governance_outcome
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.schema.governance import GovernanceAction, GovIngressProfile


@dataclass(frozen=True)
class IngressIntentView:
    """Engine return at ingress chokepoint (τ not yet appended)."""

    response_kind: str
    error_text: str = ""
    retry_count: int = 0
    max_retries: int = 0
    profile: GovIngressProfile = GovIngressProfile.PERMISSIVE


@dataclass(frozen=True)
class IngressGovDecision:
    """Governance plugin output — kernel maps to coupling, not Mealy recovery arcs."""

    action: GovernanceAction
    boundary_code: str = ""
    message: str = ""
    recoverable: bool = True
    chain: Literal["stop", "continue"] = "stop"


class IngressGovernancePlugin(Protocol):
    """Evaluate engine ingress at chokepoint (errors are signals, not embedded recovery δ)."""

    plugin_id: str

    def evaluate_ingress(
        self, intent: IngressIntentView, *, config: KernelConfig
    ) -> IngressGovDecision: ...


class KernelIngressGovernancePlugin:
    """Default — parametric ingress profiles + optional ErrorRecoveryPlugin classifier."""

    def evaluate_ingress(
        self, intent: IngressIntentView, *, config: KernelConfig
    ) -> IngressGovDecision:
        if intent.response_kind != "ERROR":
            action, reason = ingress_governance_outcome(
                response_kind=intent.response_kind, profile=intent.profile
            )
            return IngressGovDecision(action=action, message=reason)

        plugin: ErrorRecoveryPlugin | None = config.error_recovery_plugin
        if plugin is not None:
            from mas.runtime.boundary.gov.error_recovery import IngressErrorContext

            decision = plugin.decide(
                IngressErrorContext(
                    response_kind=intent.response_kind,
                    error_text=intent.error_text,
                    retry_count=intent.retry_count,
                    max_retries=intent.max_retries,
                    profile=intent.profile,
                )
            )
            return IngressGovDecision(
                action=map_recovery_to_governance(decision),
                boundary_code=decision.boundary_code,
                message=decision.message,
                recoverable=decision.recoverable,
            )

        action, reason = ingress_governance_outcome(
            response_kind=intent.response_kind, profile=intent.profile
        )
        return IngressGovDecision(action=action, message=reason)


def evaluate_ingress_at_chokepoint(
    intent: IngressIntentView,
    *,
    config: KernelConfig,
    plugin: IngressGovernancePlugin | None = None,
) -> IngressGovDecision:
    impl = plugin or KernelIngressGovernancePlugin()
    return impl.evaluate_ingress(intent, config=config)
