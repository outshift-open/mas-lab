#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Kernel configuration — mirrors TLA CONSTANT profile flags."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mas.runtime.agent_defaults import default_pattern_plugin_id
from mas.runtime.schema.governance import GovIngressProfile, GovPolicyProfile

if TYPE_CHECKING:
    from mas.runtime.boundary.gov.policy_engine import GovernancePolicyEngine
    from mas.runtime.boundary.gov.error_recovery import ErrorRecoveryPlugin


@dataclass(frozen=True)
class KernelConfig:
    pattern_plugin_id: str = field(default_factory=default_pattern_plugin_id)
    gov_policy_profile: GovPolicyProfile = GovPolicyProfile.BLOCK_DESTRUCTIVE
    gov_ingress_profile: GovIngressProfile = GovIngressProfile.PERMISSIVE
    gov_block_destructive: bool = False
    gov_trigger_destructive: bool = False
    max_gov_retries: int = 2
    hitl_on_tool: bool = False
    hitl_on_tool_result: bool = False
    hitl_once_per_turn: bool = False
    egress_governance_plugin: object | None = field(default=None, compare=False)
    enable_memory_egress: bool = False
    enable_transport_egress: bool = False
    max_cot_pass: int = 1
    parallel_tool_calls: bool = True
    policy_engine: GovernancePolicyEngine | None = field(default=None, compare=False)
    error_recovery_plugin: ErrorRecoveryPlugin | None = field(default=None, compare=False)
    ingress_governance_plugins: tuple = field(default=(), compare=False)
    enable_governance: bool = True
    enable_envelope_observability: bool = True
