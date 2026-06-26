#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Sample governance plugin — reference HITL on tool egress and tool-result ingress."""

from __future__ import annotations

from dataclasses import dataclass

from mas.runtime.boundary.gov.ingress_plugin import (
    IngressGovDecision,
    IngressIntentView,
    KernelIngressGovernancePlugin,
)
from mas.runtime.boundary.gov.policy import EgressIntentView, resolve_egress_governance
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import GovDecision
from mas.runtime.schema.governance import GovernanceAction


@dataclass(frozen=True)
class SampleGovernanceConfig:
    hitl_on_tool: bool = False
    hitl_on_tool_result: bool = False
    hitl_once_per_turn: bool = False
    gov_trigger_destructive: bool = False
    gov_block_destructive: bool = False
    gov_policy_profile: str = "BLOCK_DESTRUCTIVE"


class SampleGovernancePlugin:
    """Manifest-driven governance — maps plugin config to egress/ingress decisions."""

    plugin_id = "sample_governance@v1"

    def __init__(self, **raw: object) -> None:
        self._cfg = SampleGovernanceConfig(
            hitl_on_tool=bool(raw.get("hitl_on_tool", False)),
            hitl_on_tool_result=bool(raw.get("hitl_on_tool_result", False)),
            hitl_once_per_turn=bool(raw.get("hitl_once_per_turn", False)),
            gov_trigger_destructive=bool(raw.get("gov_trigger_destructive", False)),
            gov_block_destructive=bool(raw.get("gov_block_destructive", False)),
            gov_policy_profile=str(raw.get("gov_policy_profile") or "BLOCK_DESTRUCTIVE"),
        )

    @property
    def config(self) -> SampleGovernanceConfig:
        return self._cfg

    def evaluate_egress(self, intent: EgressIntentView, *, config: KernelConfig) -> GovDecision:
        if self._cfg.hitl_on_tool and intent.op == "TOOL_CALL":
            return GovDecision.HITL
        action = resolve_egress_governance(
            intent,
            profile=config.gov_policy_profile,
            block_destructive=self._cfg.gov_block_destructive or config.gov_block_destructive,
            policy_engine=config.policy_engine,
            hitl_gov_override=False,
        )
        return GovDecision(action.value)

    def evaluate_ingress(
        self, intent: IngressIntentView, *, config: KernelConfig
    ) -> IngressGovDecision:
        if self._cfg.hitl_on_tool_result and intent.response_kind == "TOOL_RESULT":
            return IngressGovDecision(action=GovernanceAction.HITL)
        return KernelIngressGovernancePlugin().evaluate_ingress(intent, config=config)
