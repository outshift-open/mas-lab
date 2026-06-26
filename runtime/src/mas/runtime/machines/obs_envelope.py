#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""M_obs envelope δ — steps on every σ; emits activity start/end for spans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mas.runtime.schema.envelope import EnvelopeSymbol
from mas.runtime.schema.observability import ObsPhase

if TYPE_CHECKING:
    from mas.runtime.kernel.envelope import EnvelopeContext


_SYMBOL_ACTIVITY: dict[EnvelopeSymbol, str] = {
    EnvelopeSymbol.OBS_WRAP_GOV_AUTHORIZE_START: "obs_wrap_gov_authorize",
    EnvelopeSymbol.OBS_WRAP_GOV_AUTHORIZE_END: "obs_wrap_gov_authorize",
    EnvelopeSymbol.GOV_AUTHORIZE_START: "gov_authorize",
    EnvelopeSymbol.GOV_AUTHORIZE_END: "gov_authorize",
    EnvelopeSymbol.GOVERNANCE_AUTHORIZE: "governance_authorize",
    EnvelopeSymbol.OBS_WRAP_GOV_VALIDATE_START: "obs_wrap_gov_validate",
    EnvelopeSymbol.OBS_WRAP_GOV_VALIDATE_END: "obs_wrap_gov_validate",
    EnvelopeSymbol.GOV_VALIDATE_START: "gov_validate",
    EnvelopeSymbol.GOV_VALIDATE_END: "gov_validate",
    EnvelopeSymbol.GOVERNANCE_VALIDATE: "governance_validate",
    EnvelopeSymbol.CONTRACT_START: "contract_call",
    EnvelopeSymbol.CONTRACT_END: "contract_call",
    EnvelopeSymbol.OBSERVABILITY_PRE_EXECUTE: "observability_pre_execute",
    EnvelopeSymbol.OBSERVABILITY_POST_EXECUTE: "observability_post_execute",
    EnvelopeSymbol.CONTRACT_EXECUTE: "contract_execute",
}

_SYMBOL_BOUNDARY: dict[EnvelopeSymbol, str] = {
    EnvelopeSymbol.OBS_WRAP_GOV_AUTHORIZE_START: "start",
    EnvelopeSymbol.OBS_WRAP_GOV_AUTHORIZE_END: "end",
    EnvelopeSymbol.GOV_AUTHORIZE_START: "start",
    EnvelopeSymbol.GOV_AUTHORIZE_END: "end",
    EnvelopeSymbol.GOV_VALIDATE_START: "start",
    EnvelopeSymbol.GOV_VALIDATE_END: "end",
    EnvelopeSymbol.OBS_WRAP_GOV_VALIDATE_START: "start",
    EnvelopeSymbol.OBS_WRAP_GOV_VALIDATE_END: "end",
    EnvelopeSymbol.CONTRACT_START: "start",
    EnvelopeSymbol.CONTRACT_END: "end",
    EnvelopeSymbol.OBSERVABILITY_PRE_EXECUTE: "start",
    EnvelopeSymbol.OBSERVABILITY_POST_EXECUTE: "end",
    EnvelopeSymbol.CONTRACT_EXECUTE: "event",
}

_SYMBOL_PHASE: dict[EnvelopeSymbol, ObsPhase] = {
    EnvelopeSymbol.GOVERNANCE_AUTHORIZE: ObsPhase.AUTHZ,
    EnvelopeSymbol.GOVERNANCE_VALIDATE: ObsPhase.VALID,
    EnvelopeSymbol.OBSERVABILITY_PRE_EXECUTE: ObsPhase.OBSERVABILITY_PRE,
    EnvelopeSymbol.OBSERVABILITY_POST_EXECUTE: ObsPhase.RESULT,
    EnvelopeSymbol.CONTRACT_EXECUTE: ObsPhase.EXECUTE,
}


@dataclass
class ObsEnvelopeMachine:
    """M_obs_j — records every envelope σ (span bookends via start/end events)."""

    machine_id: str = "M_obs"

    def step(self, symbol: EnvelopeSymbol, ctx: EnvelopeContext) -> None:
        obs = ctx.observability
        if obs is None:
            return
        activity = _SYMBOL_ACTIVITY.get(symbol, symbol.value)
        boundary = _SYMBOL_BOUNDARY.get(symbol, "event")
        phase = _SYMBOL_PHASE.get(symbol, ObsPhase.REQUEST)
        payload: dict[str, Any] = {
            "symbol": symbol.value,
            "activity": activity,
            "boundary": boundary,
            "contract": ctx.contract.value,
            "operation": ctx.operation,
            "op": ctx.scheduled_op,
        }
        if symbol == EnvelopeSymbol.GOVERNANCE_AUTHORIZE:
            payload["decision"] = ctx.gov_decision
            payload["hook"] = "egress"
            payload["checkpoint"] = "authorize"
        elif symbol == EnvelopeSymbol.GOVERNANCE_VALIDATE:
            payload["decision"] = ctx.gov_decision
            payload["hook"] = "ingress"
            payload["checkpoint"] = "validate"
        elif symbol in (
            EnvelopeSymbol.OBSERVABILITY_PRE_EXECUTE,
            EnvelopeSymbol.OBSERVABILITY_POST_EXECUTE,
        ):
            payload["tool_name"] = ctx.tool_name
            if ctx.ingress_event is not None:
                payload["response_kind"] = ctx.ingress_event.response_kind
        elif symbol == EnvelopeSymbol.CONTRACT_EXECUTE:
            payload["tool_name"] = ctx.tool_name
            payload["tool_arguments"] = dict(ctx.tool_arguments or {})
            io_record = getattr(obs, "record_engine_io", None)
            if callable(io_record):
                io_record(
                    correlation_id=ctx.correlation_id,
                    op=ctx.scheduled_op,
                    destructive=ctx.destructive,
                    tool_name=ctx.tool_name,
                )
        elif symbol == EnvelopeSymbol.OBSERVABILITY_POST_EXECUTE and ctx.ingress_event is not None:
            ev = ctx.ingress_event
            ret_record = getattr(obs, "record_engine_io_return", None)
            if callable(ret_record):
                ret_record(
                    correlation_id=ctx.correlation_id,
                    op=ctx.scheduled_op,
                    text=ev.text,
                    next_step=ev.next_step,
                    response_kind=ev.response_kind,
                )
        record = getattr(obs, "record_envelope_activity", None)
        if callable(record):
            record(
                symbol=symbol.value,
                activity=activity,
                boundary=boundary,
                phase=phase,
                correlation_id=ctx.correlation_id,
                machine_id=self.machine_id,
                payload=payload,
            )
