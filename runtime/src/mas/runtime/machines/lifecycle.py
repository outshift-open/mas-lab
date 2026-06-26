#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_ctrl — lifecycle transitions aligned to TLA PauseAgent / ResumeAgent / AbortAgent."""

from __future__ import annotations

from mas.runtime.schema.egress import EgressSymbol, NoOp
from mas.runtime.schema.ingress import (
    IngressSymbol,
    LifecycleAbort,
    LifecyclePause,
    LifecycleResume,
)
from mas.runtime.kernel.state import LifecycleState, QProduct


def step_lifecycle(q: QProduct, event: IngressSymbol) -> list[EgressSymbol]:
    from mas.runtime.kernel.coupling import apply_lifecycle_abort, apply_lifecycle_pause

    if isinstance(event, LifecyclePause) and q.ctrl == LifecycleState.RUNNING:
        q.ctrl = LifecycleState.PAUSED
        apply_lifecycle_pause(q)
        return [NoOp()]

    if isinstance(event, LifecycleResume) and q.ctrl == LifecycleState.PAUSED:
        q.ctrl = LifecycleState.RUNNING
        return [NoOp()]

    if isinstance(event, LifecycleAbort) and q.ctrl != LifecycleState.STOPPED:
        apply_lifecycle_abort(q)
        return [NoOp()]

    return []
