#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Built-in MCE eval provider — stock session metrics plus registered EvalMetrics."""

from __future__ import annotations

from mas.library.eval.evaluator import EvalProvider
from mas.library.eval.mce.catalog import METRIC_MAP
from mas.library.eval.metrics import EvalMetric
from mas.library.eval.metrics.stock import stock_metric


class MCEProvider(EvalProvider):
    """The MCE provider. Stock snake_case ids live here; plugins register here."""

    name = "mce"

    def resolve_metric(self, metric_id: str) -> EvalMetric | None:
        hosted = super().resolve_metric(metric_id)
        if hosted is not None:
            return hosted
        return stock_metric(metric_id)

    def metric_ids(self) -> list[str]:
        return list(METRIC_MAP) + super().metric_ids()

    def available_metrics(self) -> list[str]:
        return self.metric_ids()

    def register_metric(self, metric: EvalMetric) -> None:
        metric_id = str(getattr(metric, "metric_id", "") or "").strip()
        if metric_id in METRIC_MAP:
            raise ValueError(f"Metric id {metric_id!r} collides with stock MCE")
        super().register_metric(metric)
