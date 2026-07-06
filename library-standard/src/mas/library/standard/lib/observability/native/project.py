#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pure projection helpers — reusable inside export plugins (not a primary ctl path)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mas.library.standard.lib.observability.native.envelope import CONTRACT_SUMMAND, stamp_envelope_fields
from mas.library.standard.lib.observability.native.transform import EventTransform, TransformContext
from mas.runtime.boundary.obs.transition import TransitionEvent

if TYPE_CHECKING:
    from mas.runtime.schema.observability import ObservabilityEvent


def boundary_dict_from_transition(event: TransitionEvent) -> dict:
    """Rebuild ctl transform input from a kernel TransitionEvent."""
    out = {
        "_source": "boundary",
        "kind": event.boundary_kind,
        "correlation_id": event.correlation_id,
        "payload": dict(event.attributes),
    }
    if event.call_id is not None:
        out["call_id"] = event.call_id
    if event.parent_call_id is not None:
        out["parent_call_id"] = event.parent_call_id
    return out


def boundary_dict_from_observability_event(event: ObservabilityEvent) -> dict:
    payload = event.model_dump(mode="json")
    payload["_source"] = "boundary"
    return payload


def project_records(
    record: dict,
    *,
    transforms: list[EventTransform],
    ctx: TransformContext,
    mas_id: str = "",
    session_id: str = "",
    transition: TransitionEvent | None = None,
) -> list[dict]:
    """Run a transform chain on one ingest record (side-effect free)."""
    records = [dict(record)]
    for transform in transforms:
        next_records: list[dict] = []
        for rec in records:
            next_records.extend(transform.transform(rec, ctx=ctx))
        records = next_records

    transition_summand = ""
    transition_mealy = ""
    if transition is not None:
        transition_summand = CONTRACT_SUMMAND.get(transition.contract_id, transition.contract_id)
        transition_mealy = transition.mealy_symbol

    return [
        stamp_envelope_fields(
            _apply_transition_ids(
                rec,
                transition=transition,
            ),
            mas_id=mas_id,
            session_id=session_id,
            transition_mealy_symbol=transition_mealy,
            transition_summand=transition_summand,
        )
        for rec in records
    ]


def _apply_transition_ids(rec: dict, *, transition: TransitionEvent | None) -> dict:
    """Propagate kernel call_id / parent_call_id when transform did not set them."""
    out = dict(rec)
    if transition is None:
        return out
    if transition.call_id and "call_id" not in out:
        out["call_id"] = transition.call_id
    if transition.parent_call_id and "parent_call_id" not in out:
        out["parent_call_id"] = transition.parent_call_id
    return out


__all__ = ["boundary_dict_from_transition", "boundary_dict_from_observability_event", "project_records"]
