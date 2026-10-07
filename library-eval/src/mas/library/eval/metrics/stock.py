#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stock MCE session metrics as :class:`EvalMetric`s on the MCE provider."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from mas.library.eval.evaluator import MetricScore
from mas.library.eval.mce.catalog import METRIC_MAP, lookup
from mas.library.eval.metrics import EvalMetric, MetricContext, RunInputs, normalize_score
from mas.library.eval.metrics.scope import scope_details


class StockMceMetric(EvalMetric):
    """One snake_case MCE session metric. Batched: one trace fetch per run."""

    aggregation_level = "session"
    input_kinds = frozenset({"native_trace"})
    requires_llm = True
    batch_key = "mce_session"
    unit = "mas"
    evidence = "io"

    def __init__(self, metric_id: str) -> None:
        spec = lookup(metric_id)
        if spec is None or spec.snake != metric_id:
            raise ValueError(f"{metric_id!r} is not a stock MCE session id")
        self.metric_id = metric_id
        self.unit = spec.unit  # type: ignore[assignment]
        self.evidence = spec.evidence  # type: ignore[assignment]
        self.description = f"Stock MCE session metric {metric_id} (unit={spec.unit}, evidence={spec.evidence})."

    async def compute(self, inputs: RunInputs, ctx: MetricContext) -> MetricScore:
        batch = await self.compute_batch([self], inputs, ctx)
        return batch[self.metric_id]

    @classmethod
    async def compute_batch(
        cls,
        metrics: Sequence[EvalMetric],
        inputs: RunInputs,
        ctx: MetricContext,
    ) -> dict[str, MetricScore]:
        from mas.library.eval.mce.runner import compute_session_metrics

        family = [m for m in metrics if isinstance(m, StockMceMetric)]
        try:
            trace = inputs.require("native_trace")
        except FileNotFoundError as exc:
            err = str(exc)
            return {m.metric_id: {"value": None, "reasoning": "", "error": err} for m in family}
        names = [m.metric_id for m in family]
        raw = await asyncio.to_thread(
            compute_session_metrics,
            trace,
            names,
            response_agent_id=ctx.response_agent_id,
        )
        quality = raw.pop("__run_quality__", None)
        if quality:
            ctx.quality_parts.append(quality)
        by_id = {m.metric_id: m for m in family}
        out: dict[str, MetricScore] = {}
        for name, score in raw.items():
            metric = by_id.get(name)
            details = dict(score.get("details") or {})
            if metric is not None:
                details.update(scope_details(metric.unit, metric.evidence))
            payload = dict(score)
            payload["details"] = details
            out[name] = normalize_score(payload)
        return out


def stock_metric(metric_id: str) -> StockMceMetric | None:
    """Return a :class:`StockMceMetric` for a snake_case catalog id, else ``None``."""
    if metric_id not in METRIC_MAP:
        return None
    return StockMceMetric(metric_id)
