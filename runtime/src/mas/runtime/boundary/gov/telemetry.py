#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance checkpoint telemetry — before/after decisions at egress and ingress."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mas.runtime.kernel.runtime_context import get_governance_observability
from mas.runtime.schema.observability import ObsEventKind, ObsPhase

if TYPE_CHECKING:
    from mas.runtime.boundary.obs.operator import ObservabilityOperator


def bind_governance_observability(recorder: ObservabilityOperator | None) -> None:
    """Legacy bind — prefer :func:`runtime_context.runtime_binding` per feed."""
    from mas.runtime.kernel.runtime_context import set_governance_observability

    set_governance_observability(recorder)


def get_bound_observability() -> ObservabilityOperator | None:
    return get_governance_observability()


def record_governance_checkpoint(
    *,
    hook: str,
    phase: str,
    decision: str = "",
    correlation_id: int = 0,
    policy_name: str = "sample_governance",
) -> None:
    _recorder = get_governance_observability()
    if _recorder is None:
        return
    obs_phase = ObsPhase.AUTHZ if hook == "egress" else ObsPhase.RESULT
    if phase == "after" and decision:
        obs_phase = ObsPhase.VALID
    _recorder.record_governance_decision(
        hook=hook,
        phase=phase,
        decision=decision,
        correlation_id=correlation_id,
        policy_name=policy_name,
        obs_phase=obs_phase,
    )
