#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Bridge kernel ObservabilityOperator → ctl emission pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from mas.ctl.adapters.obs.pipeline import ObservabilityPipeline
from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.schema.egress import EgressSymbol
from mas.runtime.schema.ingress import IngressSymbol
from mas.runtime.kernel.state import QProduct


@dataclass
class FanOutObservabilitySink:
    """In-memory audit (M_obs) + optional ctl pipeline emission."""

    operator: ObservabilityOperator
    pipeline: ObservabilityPipeline | None = None

    def record_ingress(self, event: IngressSymbol, q: QProduct) -> None:
        self.operator.record_ingress(event, q)
        self._maybe_ingest()

    def record_egress(self, sym: EgressSymbol, q: QProduct) -> None:
        self.operator.record_egress(sym, q)
        self._maybe_ingest()

    def record_governance_decision(self, **kwargs) -> None:
        self.operator.record_governance_decision(**kwargs)
        self._maybe_ingest()

    def record_context_mutation(self, **kwargs) -> None:
        self.operator.record_context_mutation(**kwargs)
        self._maybe_ingest()

    def record_context_assembled(self, **kwargs) -> None:
        self.operator.record_context_assembled(**kwargs)
        self._maybe_ingest()

    def record_engine_llm_return(self, **kwargs) -> None:
        self.operator.record_engine_llm_return(**kwargs)
        self._maybe_ingest()

    def _maybe_ingest(self) -> None:
        if self.pipeline is not None and self.operator.events:
            self.pipeline.ingest_boundary(self.operator.events[-1])

    @property
    def events(self):
        return self.operator.events

    def audit(self):
        return self.operator.audit()


def attach_observability(instance, pipeline: ObservabilityPipeline | None) -> None:
    """Replace driver observability with fan-out sink when pipeline enabled."""
    if pipeline is None:
        return
    driver = instance.driver
    inner = driver.observability or ObservabilityOperator()
    driver.observability = FanOutObservabilitySink(operator=inner, pipeline=pipeline)
