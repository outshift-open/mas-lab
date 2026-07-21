#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Contract-call envelopes — execute_contract_call and egress/ingress σ sequences."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

from mas.runtime.boundary.gov.ingress_chain import evaluate_ingress_chain
from mas.runtime.boundary.gov.ingress_plugin import IngressGovDecision, IngressIntentView
from mas.runtime.boundary.gov.plugin import evaluate_egress_at_chokepoint
from mas.runtime.boundary.gov.policy import EgressIntentView
from mas.runtime.kernel.coupling import GovDecision
from mas.runtime.schema.envelope import (
    ContractKind,
    EnvelopeSymbol,
    resolve_egress_symbols,
    resolve_ingress_symbols,
)
from mas.runtime.schema.governance import GovernanceAction

if TYPE_CHECKING:
    from mas.runtime.boundary.obs.operator import ObservabilityOperator
    from mas.runtime.kernel.config import KernelConfig
    from mas.runtime.kernel.state import QProduct
    from mas.runtime.schema.ingress import EngineIoReturn
else:
    from mas.runtime.schema.ingress import EngineIoReturn


@dataclass
class EnvelopeContext:
    """Shared tape slice for one contract-call envelope."""

    q: QProduct
    correlation_id: int
    contract: ContractKind
    operation: str = "call"
    scheduled_op: str = "TOOL_CALL"
    observability: ObservabilityOperator | None = None
    config: KernelConfig | None = None
    tool_name: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    ingress_event: EngineIoReturn | None = None
    gov_decision: str = ""
    gov_reason: str = ""
    policy_name: str = "sample_governance"
    destructive: bool = False
    hitl_gov_override: bool = False


def execute_contract_call(
    contract: ContractKind,
    operation: str,
    ctx: EnvelopeContext,
    *,
    execute_fn: Callable[[], Any] | None = None,
) -> Any:
    """Full seven-symbol envelope: authorize → pre → execute → post → validate.

    ``execute_fn`` runs only between OBSERVABILITY_PRE_EXECUTE and POST (impure I/O).
    When omitted, caller performs I/O across the kernel/driver boundary.
    """
    composer = get_product_composer(ctx.config)
    egress, ingress = _envelope_symbol_lists(ctx)
    result: Any = None

    for symbol in egress:
        if symbol == EnvelopeSymbol.GOVERNANCE_AUTHORIZE:
            ctx.gov_decision = _evaluate_egress(ctx).value
        composer.step(symbol, ctx)

    if execute_fn is not None:
        composer.step(EnvelopeSymbol.CONTRACT_EXECUTE, ctx)
        result = execute_fn()
        ctx.ingress_event = EngineIoReturn(
            correlation_id=ctx.correlation_id,
            response_kind="TOOL_RESULT" if ctx.scheduled_op == "TOOL_CALL" else "MODEL_TEXT",
            next_step="STOP",
            text=str(result) if result is not None else "",
        )
        for symbol in ingress:
            if symbol == EnvelopeSymbol.GOVERNANCE_VALIDATE:
                decision = _evaluate_ingress(ctx)
                ctx.gov_decision = decision.action.value
            composer.step(symbol, ctx)
    return result


def run_egress_authorize_envelope(ctx: EnvelopeContext) -> GovDecision:
    """Kernel egress chokepoint: obs⊗gov wrap + contract start + obs pre."""
    composer = get_product_composer(ctx.config)
    decision = GovDecision.ALLOW
    for symbol in resolve_egress_symbols(**_envelope_flags(ctx)):
        if symbol == EnvelopeSymbol.GOVERNANCE_AUTHORIZE:
            decision = _evaluate_egress(ctx)
            ctx.gov_decision = decision.value
        composer.step(symbol, ctx)
    return decision


def run_ingress_validate_envelope(ctx: EnvelopeContext) -> IngressGovDecision:
    """Kernel ingress chokepoint: obs post + contract end + obs⊗gov validate wrap."""
    composer = get_product_composer(ctx.config)
    decision = IngressGovDecision(action=GovernanceAction.ALLOW)
    for symbol in resolve_ingress_symbols(**_envelope_flags(ctx)):
        if symbol == EnvelopeSymbol.GOVERNANCE_VALIDATE:
            decision = _evaluate_ingress(ctx)
            ctx.gov_decision = decision.action.value
        composer.step(symbol, ctx)
    return decision


def run_contract_execute_obs(ctx: EnvelopeContext) -> None:
    """Emit CONTRACT_EXECUTE σ (driver invoked engine; obs records boundary)."""
    get_product_composer(ctx.config).step(EnvelopeSymbol.CONTRACT_EXECUTE, ctx)


def _envelope_flags(ctx: EnvelopeContext) -> dict[str, bool]:
    cfg = ctx.config
    return {
        "enable_governance": True if cfg is None else cfg.enable_governance,
        "enable_envelope_observability": True if cfg is None else cfg.enable_envelope_observability,
    }


def _envelope_symbol_lists(
    ctx: EnvelopeContext,
) -> tuple[tuple[EnvelopeSymbol, ...], tuple[EnvelopeSymbol, ...]]:
    flags = _envelope_flags(ctx)
    return (
        resolve_egress_symbols(**flags),
        resolve_ingress_symbols(**flags),
    )


def _evaluate_egress(ctx: EnvelopeContext) -> GovDecision:
    assert ctx.config is not None
    if not ctx.config.enable_governance:
        ctx.gov_reason = "governance disabled for this run"
        return GovDecision.ALLOW
    view = EgressIntentView(
        op=ctx.scheduled_op,  # type: ignore[arg-type]
        destructive=ctx.destructive,
        correlation_id=ctx.correlation_id,
        tool_name=ctx.tool_name,
        tool_arguments=ctx.tool_arguments,
    )
    decision, ctx.policy_name, ctx.gov_reason = evaluate_egress_at_chokepoint(
        view,
        config=ctx.config,
        hitl_gov_override=ctx.hitl_gov_override,
    )
    return decision


def _evaluate_ingress(ctx: EnvelopeContext) -> IngressGovDecision:
    assert ctx.config is not None
    if not ctx.config.enable_governance:
        ctx.gov_reason = "governance disabled for this run"
        return IngressGovDecision(action=GovernanceAction.ALLOW)
    assert ctx.ingress_event is not None
    ev = ctx.ingress_event
    decision = evaluate_ingress_chain(
        IngressIntentView(
            response_kind=ev.response_kind,
            error_text=ev.text,
            profile=ctx.config.gov_ingress_profile,
            retry_count=ctx.q.gov_retry_count,
            max_retries=ctx.config.max_gov_retries,
        ),
        config=ctx.config,
    )
    # Every built-in ingress plugin (KernelIngressGovernancePlugin,
    # SampleGovernancePlugin) always populates message; this generic fallback
    # only matters for a custom third-party plugin that doesn't.
    ctx.gov_reason = decision.message or f"{decision.action.value} (no reason supplied by ingress plugin)"
    return decision


def contract_kind_for_op(op: str) -> ContractKind:
    if op == "LLM_CALL":
        return ContractKind.MODEL
    if op == "MEMORY_OP":
        return ContractKind.MEMORY
    if op == "TRANSPORT_MSG":
        return ContractKind.TRANSPORT
    return ContractKind.TOOL


# ── Guarded product composer (M_obs ⊗ M_gov ⊗ M_capability) ─────────────


class MealyEnvelopeMachine(Protocol):
    machine_id: str

    def step(self, symbol: EnvelopeSymbol, ctx: EnvelopeContext) -> None: ...


@dataclass
class GuardedProductComposer:
    """Synchronous product: every machine steps on the same input symbol (or holds)."""

    machines: list[MealyEnvelopeMachine] = field(default_factory=list)

    def step(self, symbol: EnvelopeSymbol, ctx: EnvelopeContext) -> None:
        for machine in self.machines:
            machine.step(symbol, ctx)

    def run(self, symbols: tuple[EnvelopeSymbol, ...], ctx: EnvelopeContext) -> None:
        for symbol in symbols:
            self.step(symbol, ctx)


_composers: dict[tuple[bool, bool], GuardedProductComposer] = {}


def get_product_composer(config: KernelConfig | None = None) -> GuardedProductComposer:
    """Product M_obs ⊗ M_gov ⊗ M_capability — summands omitted when profile disables them."""
    enable_gov = True if config is None else config.enable_governance
    enable_obs = True if config is None else config.enable_envelope_observability
    key = (enable_gov, enable_obs)
    if key not in _composers:
        from mas.runtime.machines.capability_envelope import CapabilityEnvelopeMachine
        from mas.runtime.machines.gov_envelope import GovEnvelopeMachine
        from mas.runtime.machines.obs_envelope import ObsEnvelopeMachine

        machines: list[MealyEnvelopeMachine] = []
        if enable_obs:
            machines.append(ObsEnvelopeMachine())
        if enable_gov:
            machines.append(GovEnvelopeMachine())
        machines.append(CapabilityEnvelopeMachine())
        _composers[key] = GuardedProductComposer(machines=machines)
    return _composers[key]
