#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Build ingress governance plugin chain from manifest entries."""

from __future__ import annotations

from mas.runtime.boundary.gov.error_recovery import (
    ErrorRecoveryPlugin,
    map_recovery_to_governance,
)
from mas.runtime.boundary.gov.filter import GovTransitionFilter
from mas.runtime.boundary.gov.ingress_chain import RegisteredIngressPlugin
from mas.runtime.boundary.gov.ingress_plugin import IngressGovDecision, IngressIntentView
from mas.runtime.kernel.config import KernelConfig


class _ErrorRecoveryIngressAdapter:
    def __init__(self, inner: ErrorRecoveryPlugin) -> None:
        self.plugin_id = inner.plugin_id
        self._inner = inner

    def evaluate_ingress(
        self, intent: IngressIntentView, *, config: KernelConfig
    ) -> IngressGovDecision:
        from mas.runtime.boundary.gov.error_recovery import IngressErrorContext

        decision = self._inner.decide(
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


def build_ingress_governance_plugins(
    *,
    ingress_plugin_specs: list[dict],
    error_recovery_plugin: ErrorRecoveryPlugin | None,
) -> tuple[RegisteredIngressPlugin, ...]:
    entries: list[RegisteredIngressPlugin] = []

    if error_recovery_plugin is not None:
        entries.append(
            RegisteredIngressPlugin(
                plugin=_ErrorRecoveryIngressAdapter(error_recovery_plugin),
                filter=GovTransitionFilter(hook="ingress", response_kind=("ERROR",)),
                chain="stop",
            )
        )

    return tuple(entries)
