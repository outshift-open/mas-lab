#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared TransitionEvent → native record projection (plugins + pipeline steps)."""

from __future__ import annotations

import time

from mas.library.standard.lib.observability.native.project import boundary_dict_from_transition, project_records
from mas.library.standard.lib.observability.native.transform import EventTransform, TransformContext
from mas.runtime.boundary.obs.transition import TransitionEvent


def project_transition(
    event: TransitionEvent,
    *,
    transforms: list[EventTransform],
    ctx: TransformContext,
    mas_id: str = "",
    session_id: str = "",
) -> list[dict]:
    """Project one kernel or session transition to native-shaped records."""
    if event.boundary_kind == "session":
        record = {
            "_source": "session",
            "session_kind": event.mealy_symbol,
            **dict(event.attributes),
        }
        source = [record]
    else:
        source = [boundary_dict_from_transition(event)]

    out: list[dict] = []
    for rec in project_records(
        source[0],
        transforms=transforms,
        ctx=ctx,
        mas_id=mas_id,
        session_id=session_id,
        transition=event,
    ):
        rec.setdefault("timestamp", event.timestamp or time.time())
        rec.setdefault("agent_id", event.agent_id or ctx.agent_id)
        rec.setdefault("run_id", event.run_id or ctx.run_id)
        out.append(rec)
    return out
