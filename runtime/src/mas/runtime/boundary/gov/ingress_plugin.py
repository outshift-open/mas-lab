#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress governance plugins — classify engine signals; kernel applies decisions (no recovery arcs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

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
    failure_class: str = ""
    failure_code: str = ""


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


def ingress_from_profile(intent: IngressIntentView) -> IngressGovDecision:
    """Parametric default: ``gov_ingress_profile`` only. No plugin lookup."""
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
    if plugin is None:
        return ingress_from_profile(intent)
    return plugin.evaluate_ingress(intent, config=config)
