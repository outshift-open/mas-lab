#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress classifier — map FailureClass onto governance allow/retry/block/skip."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from mas.runtime.boundary.gov.error_recovery import (
    ErrorRecoveryAction,
    ErrorRecoveryDecision,
    IngressErrorContext,
    map_recovery_to_governance,
)
from mas.runtime.boundary.gov.ingress_plugin import IngressGovDecision, IngressIntentView
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import GovDecision
from mas.runtime.reliability.classes import FailureClass

PLUGIN_ID = "retry_on_error"
_GOV_ACTIONS = frozenset({"allow", "retry", "block", "skip"})


@dataclass(frozen=True)
class ErrorPolicy:
    """Ingress action after infra retries (and the breaker) have finished.

    Plugin config, not kernel state. The kernel only applies ``decide()``.
    """

    transient: str = "allow"
    unavailable: str = "allow"
    application: str = "allow"
    fatal: str = "block"

    def action_for(self, failure_class: FailureClass) -> str:
        return getattr(self, failure_class.value)

    @classmethod
    def from_mapping(cls, raw: Any, *, field_name: str = "error_policy") -> ErrorPolicy:
        from mas.runtime.spec.gov import SpecBindingError

        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise SpecBindingError(f"{field_name} must be an object")
        allowed = {"transient", "unavailable", "application", "fatal"}
        unknown = set(raw) - allowed
        if unknown:
            raise SpecBindingError(f"{field_name}: unknown field {sorted(unknown)[0]!r}")
        kwargs: dict[str, str] = {}
        for key in allowed:
            if key not in raw:
                continue
            value = str(raw[key]).strip().lower()
            if value not in _GOV_ACTIONS:
                raise SpecBindingError(
                    f"{field_name}.{key} must be one of {sorted(_GOV_ACTIONS)}, got {raw[key]!r}"
                )
            kwargs[key] = value
        return cls(**kwargs)


class RetryOnErrorPlugin:
    """Ingress ErrorRecoveryPlugin keyed by ``spec.governance[].error_policy``.

    Safe on the egress chain: it always PASSes so later plugins (for example
    ``gov_no_undeclared_tool``) still run. The kernel consults ``decide()``
    after an engine ERROR or a TOOL_RESULT that already carries a failure
    class.
    """

    plugin_id = "retry_on_error@v1"

    def __init__(self, error_policy: dict | ErrorPolicy | None = None, **_raw: object) -> None:
        self._policy = (
            error_policy
            if isinstance(error_policy, ErrorPolicy)
            else ErrorPolicy.from_mapping(error_policy)
        )

    def evaluate_egress(self, intent, *, config: KernelConfig):
        return GovDecision.ALLOW, PLUGIN_ID, "retry_on_error classifies ingress, not egress"

    def decide(self, ctx: IngressErrorContext) -> ErrorRecoveryDecision:
        try:
            klass = (
                FailureClass(ctx.failure_class)
                if ctx.failure_class
                else (
                    FailureClass.APPLICATION
                    if ctx.response_kind != "ERROR"
                    else FailureClass.FATAL
                )
            )
        except ValueError:
            klass = FailureClass.FATAL
        action = self._policy.action_for(klass)
        if action == "retry" and ctx.retry_count >= ctx.max_retries:
            action = "allow"
        mapped = {
            "allow": ErrorRecoveryAction.ALLOW,
            "retry": ErrorRecoveryAction.RETRY,
            "block": ErrorRecoveryAction.EXIT,
            "skip": ErrorRecoveryAction.SKIP,
        }[action]
        return ErrorRecoveryDecision(
            action=mapped,
            boundary_code="INGRESS_ERROR_EXIT" if mapped == ErrorRecoveryAction.EXIT else "",
            recoverable=klass != FailureClass.FATAL,
            message=f"error_policy.{klass.value}={self._policy.action_for(klass)}",
        )

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
