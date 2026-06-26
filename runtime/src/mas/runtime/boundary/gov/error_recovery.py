#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress error recovery plugins — classify engine ERROR and map to governance actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from mas.runtime.schema.governance import GovernanceAction, GovIngressProfile


class ErrorRecoveryAction(str, Enum):
    """Plugin-level decision before kernel governance mapping."""

    ALLOW = "ALLOW"  # append τ → surface finish_reason=error to operator
    RETRY = "RETRY"
    EXIT = "EXIT"  # non-recoverable — boundary error, stop workflow
    SKIP = "SKIP"  # synthetic success path (ingress SKIP)


@dataclass(frozen=True)
class IngressErrorContext:
    response_kind: str
    error_text: str
    retry_count: int
    max_retries: int
    profile: GovIngressProfile


@dataclass(frozen=True)
class ErrorRecoveryDecision:
    action: ErrorRecoveryAction
    boundary_code: str = "INGRESS_ERROR_EXIT"
    recoverable: bool = False
    message: str = ""


class ErrorRecoveryPlugin(Protocol):
    """Classify engine ERROR text and recommend ingress governance action."""

    plugin_id: str

    def decide(self, ctx: IngressErrorContext) -> ErrorRecoveryDecision: ...


def map_recovery_to_governance(decision: ErrorRecoveryDecision) -> GovernanceAction:
    if decision.action == ErrorRecoveryAction.RETRY:
        return GovernanceAction.RETRY
    if decision.action == ErrorRecoveryAction.EXIT:
        return GovernanceAction.BLOCK
    if decision.action == ErrorRecoveryAction.SKIP:
        return GovernanceAction.SKIP
    return GovernanceAction.ALLOW


def resolve_ingress_error_governance(
    *,
    response_kind: str,
    error_text: str,
    profile: GovIngressProfile,
    retry_count: int,
    max_retries: int,
    plugin: ErrorRecoveryPlugin | None = None,
) -> tuple[GovernanceAction, ErrorRecoveryDecision | None]:
    """Resolve ingress governance for engine returns (ERROR-aware)."""
    from mas.runtime.boundary.gov.policy import ingress_governance_outcome

    if response_kind != "ERROR":
        return ingress_governance_outcome(response_kind=response_kind, profile=profile), None

    ctx = IngressErrorContext(
        response_kind=response_kind,
        error_text=error_text or "",
        retry_count=retry_count,
        max_retries=max_retries,
        profile=profile,
    )
    if plugin is not None:
        decision = plugin.decide(ctx)
        return map_recovery_to_governance(decision), decision

    return ingress_governance_outcome(response_kind=response_kind, profile=profile), None
