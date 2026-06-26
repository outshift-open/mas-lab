#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance evaluator — optional LLM-as-judge outside the kernel step (LLMaaJ)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mas.runtime.boundary.gov.policy import EgressIntentView
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.coupling import GovDecision


@dataclass(frozen=True)
class GovEvaluatorIntent:
    """Input to an async/sync governance evaluator at the chokepoint."""

    hook: str  # ingress | egress
    egress: EgressIntentView | None = None
    response_kind: str = ""
    error_text: str = ""


class GovEvaluatorContract(Protocol):
    """LLMaaJ and similar — may call an LLM; invoked by the **driver**, not inside kernel δ.

    Kernel enters AUTHZ, driver calls evaluator, feeds ``GovEvaluatorReturn`` as ingress
    (same pattern as EngineContract). Filters on ``GovernancePlugin`` skip invocation
    when the transition does not match.
    """

    evaluator_id: str

    def evaluate(self, intent: GovEvaluatorIntent, *, config: KernelConfig) -> GovDecision: ...


@dataclass(frozen=True)
class GovEvaluatorReturn:
    """Driver ingress after evaluator completes — maps to gov decision application."""

    request_id: int
    decision: GovDecision
    rationale: str = ""
