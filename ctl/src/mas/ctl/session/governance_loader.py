#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Build governance plugin chain from manifest entries."""

from __future__ import annotations

from typing import Any

from mas.runtime.boundary.gov.filter import GovTransitionFilter
from mas.runtime.boundary.gov.ingress_chain import RegisteredIngressPlugin
from mas.runtime.boundary.gov.sample import SampleGovernancePlugin
from mas.runtime.kernel.config import KernelConfig


def build_governance_plugins(
    *,
    plugin_names: list[str],
    plugin_configs: dict[str, dict[str, Any]],
) -> tuple[SampleGovernancePlugin | None, tuple[RegisteredIngressPlugin, ...], dict[str, Any]]:
    """Instantiate sample governance plugin and ingress chain from manifest list."""
    flat: dict[str, Any] = {}
    egress: SampleGovernancePlugin | None = None
    ingress_entries: list[RegisteredIngressPlugin] = []

    for name in plugin_names:
        cfg = dict(plugin_configs.get(name) or {})
        if name in {"sample_governance", "sample_governance@v1"}:
            egress = SampleGovernancePlugin(**cfg)
            flat.update(cfg)
            if egress.config.hitl_on_tool_result:
                ingress_entries.append(
                    RegisteredIngressPlugin(
                        plugin=egress,
                        filter=GovTransitionFilter(hook="ingress", response_kind=("TOOL_RESULT",)),
                        chain="stop",
                    )
                )

    return egress, tuple(ingress_entries), flat
