#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Repeat-aware error recovery that requests session-level rollback."""

from __future__ import annotations

from dataclasses import dataclass, field

from mas.runtime.boundary.gov.error_recovery import (
    ErrorRecoveryAction,
    ErrorRecoveryDecision,
    IngressErrorContext,
    map_recovery_to_governance,
)
from mas.runtime.boundary.gov.ingress_plugin import IngressGovDecision, IngressIntentView
from mas.runtime.kernel.config import KernelConfig


@dataclass
class BacktrackOnErrorPlugin:
    """Retry a repeated engine error until its signature reaches a threshold."""

    repeat_threshold: int = 2
    plugin_id: str = "backtrack_on_error@v1"
    _last_signature: str = field(default="", init=False, repr=False)
    _repeat_count: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.repeat_threshold, int)
            or isinstance(self.repeat_threshold, bool)
            or self.repeat_threshold < 1
        ):
            raise ValueError("repeat_threshold must be an integer >= 1")

    def decide(self, ctx: IngressErrorContext) -> ErrorRecoveryDecision:
        """Retry first failures and request rollback after repeated identical errors."""
        signature = ctx.error_text
        if ctx.retry_count == 0 or signature != self._last_signature:
            self._last_signature = signature
            self._repeat_count = 1
        else:
            self._repeat_count += 1

        if self._repeat_count >= self.repeat_threshold:
            return ErrorRecoveryDecision(
                action=ErrorRecoveryAction.BACKTRACK,
                recoverable=True,
                message=ctx.error_text,
            )
        if ctx.retry_count < ctx.max_retries:
            return ErrorRecoveryDecision(action=ErrorRecoveryAction.RETRY, recoverable=True)
        return ErrorRecoveryDecision(action=ErrorRecoveryAction.ALLOW, recoverable=True)

    def evaluate_ingress(
        self, intent: IngressIntentView, *, config: KernelConfig
    ) -> IngressGovDecision:
        decision = self.decide(
            IngressErrorContext(
                response_kind=intent.response_kind,
                error_text=intent.error_text,
                retry_count=intent.retry_count,
                max_retries=intent.max_retries,
                profile=intent.profile,
                failure_class=intent.failure_class,
                failure_code=intent.failure_code,
            )
        )
        return IngressGovDecision(
            action=map_recovery_to_governance(decision),
            boundary_code=decision.boundary_code,
            message=decision.message,
            recoverable=decision.recoverable,
            chain=decision.chain,
        )