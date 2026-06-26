#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Formal envelope input alphabet — one σ per product step (Mealy composition)."""

from __future__ import annotations

from enum import Enum


class ContractKind(str, Enum):
    """Capability contract dimension."""

    TOOL = "tool"
    MODEL = "model"
    MEMORY = "memory"
    TRANSPORT = "transport"


class EnvelopeSymbol(str, Enum):
    """Input symbols for a contract-call envelope (tool/model share gov/obs slots)."""

    # ── Governance authorize (pre-execute) ───────────────────────────────
    OBS_WRAP_GOV_AUTHORIZE_START = "obs_wrap_gov_authorize_start"
    GOV_AUTHORIZE_START = "gov_authorize_start"
    GOVERNANCE_AUTHORIZE = "governance_authorize"
    GOV_AUTHORIZE_END = "gov_authorize_end"
    OBS_WRAP_GOV_AUTHORIZE_END = "obs_wrap_gov_authorize_end"

    # ── Capability execute ───────────────────────────────────────────────
    CONTRACT_START = "contract_start"
    OBSERVABILITY_PRE_EXECUTE = "observability_pre_execute"
    CONTRACT_EXECUTE = "contract_execute"
    OBSERVABILITY_POST_EXECUTE = "observability_post_execute"
    CONTRACT_END = "contract_end"

    # ── Governance validate (post-execute) ─────────────────────────────
    OBS_WRAP_GOV_VALIDATE_START = "obs_wrap_gov_validate_start"
    GOV_VALIDATE_START = "gov_validate_start"
    GOVERNANCE_VALIDATE = "governance_validate"
    GOV_VALIDATE_END = "gov_validate_end"
    OBS_WRAP_GOV_VALIDATE_END = "obs_wrap_gov_validate_end"


def resolve_egress_symbols(
    *,
    enable_governance: bool = True,
    enable_envelope_observability: bool = True,
) -> tuple[EnvelopeSymbol, ...]:
    """Collapsed σ list when obs/gov summands are disabled (TLA CONSTANT profile)."""
    symbols: list[EnvelopeSymbol] = []
    if enable_governance:
        if enable_envelope_observability:
            symbols.extend(
                (
                    EnvelopeSymbol.OBS_WRAP_GOV_AUTHORIZE_START,
                    EnvelopeSymbol.GOV_AUTHORIZE_START,
                    EnvelopeSymbol.GOVERNANCE_AUTHORIZE,
                    EnvelopeSymbol.GOV_AUTHORIZE_END,
                    EnvelopeSymbol.OBS_WRAP_GOV_AUTHORIZE_END,
                )
            )
        else:
            symbols.extend(
                (
                    EnvelopeSymbol.GOV_AUTHORIZE_START,
                    EnvelopeSymbol.GOVERNANCE_AUTHORIZE,
                    EnvelopeSymbol.GOV_AUTHORIZE_END,
                )
            )
    symbols.append(EnvelopeSymbol.CONTRACT_START)
    if enable_envelope_observability:
        symbols.append(EnvelopeSymbol.OBSERVABILITY_PRE_EXECUTE)
    return tuple(symbols)


def resolve_ingress_symbols(
    *,
    enable_governance: bool = True,
    enable_envelope_observability: bool = True,
) -> tuple[EnvelopeSymbol, ...]:
    """Ingress σ after execute — post-execute, contract end, validate wrap."""
    symbols: list[EnvelopeSymbol] = []
    if enable_envelope_observability:
        symbols.append(EnvelopeSymbol.OBSERVABILITY_POST_EXECUTE)
    symbols.append(EnvelopeSymbol.CONTRACT_END)
    if enable_governance:
        if enable_envelope_observability:
            symbols.extend(
                (
                    EnvelopeSymbol.OBS_WRAP_GOV_VALIDATE_START,
                    EnvelopeSymbol.GOV_VALIDATE_START,
                    EnvelopeSymbol.GOVERNANCE_VALIDATE,
                    EnvelopeSymbol.GOV_VALIDATE_END,
                    EnvelopeSymbol.OBS_WRAP_GOV_VALIDATE_END,
                )
            )
        else:
            symbols.extend(
                (
                    EnvelopeSymbol.GOV_VALIDATE_START,
                    EnvelopeSymbol.GOVERNANCE_VALIDATE,
                    EnvelopeSymbol.GOV_VALIDATE_END,
                )
            )
    return tuple(symbols)


# Full product profile (obs + gov + capability).
EGRESS_ENVELOPE_SYMBOLS: tuple[EnvelopeSymbol, ...] = resolve_egress_symbols()
INGRESS_ENVELOPE_SYMBOLS: tuple[EnvelopeSymbol, ...] = resolve_ingress_symbols()
