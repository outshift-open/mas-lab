#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Build ingress governance plugin chain from already-instantiated plugins."""

from __future__ import annotations

from mas.runtime.boundary.gov.filter import GovTransitionFilter
from mas.runtime.boundary.gov.ingress_chain import RegisteredIngressPlugin


def build_ingress_governance_plugins(
    *,
    error_recovery_plugin: object | None = None,
) -> tuple[RegisteredIngressPlugin, ...]:
    """``build_kernel_config`` already puts recovery plugins on the chain.

    This helper is for tests/callers that already hold a plugin instance
    with ``evaluate_ingress``.
    """
    if error_recovery_plugin is None:
        return ()
    return (
        RegisteredIngressPlugin(
            plugin=error_recovery_plugin,  # type: ignore[arg-type]
            filter=GovTransitionFilter(hook="ingress", response_kind=("ERROR",)),
            chain="stop",
        ),
    )
