#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Dispatch M_dp transitions through the registered design-pattern plugin."""

from __future__ import annotations

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.machines.design_pattern.protocol import DesignPatternPlugin
from mas.runtime.schema.egress import EgressSymbol
from mas.runtime.schema.ingress import IngressSymbol
from mas.runtime.kernel.state import QProduct, RunLedger


def step_design_pattern(
    plugin: DesignPatternPlugin,
    q: QProduct,
    run: RunLedger,
    event: IngressSymbol,
    *,
    config: KernelConfig,
) -> list[EgressSymbol]:
    from mas.runtime.schema.egress import RaiseBoundaryError

    try:
        return plugin.handle_event(q, run, event, config=config)
    except Exception as exc:
        return [
            RaiseBoundaryError(
                code="PLUGIN_ERROR",
                message=str(exc) or exc.__class__.__name__,
                recoverable=True,
            )
        ]
