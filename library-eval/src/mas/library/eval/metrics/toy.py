#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Toy eval metric shipped with library-eval for tests and docs."""

from __future__ import annotations

from mas.library.eval.evaluator import MetricScore
from mas.library.eval.metrics import EvalMetric, MetricContext, RunInputs


class ToyEchoMetric(EvalMetric):
    """Returns 1.0 when a native trace file exists. Polarity: 1 = present."""

    metric_id = "toy_echo"
    description = (
        "Example session metric. value 1.0 when the native trace exists, "
        "null with an error when it does not. Does not call an LLM."
    )
    unit = "mas"
    evidence = "trajectory"
    requires_llm = False

    async def compute(self, inputs: RunInputs, ctx: MetricContext) -> MetricScore:
        path = inputs.require("native_trace")
        size = path.stat().st_size
        return {
            "value": 1.0,
            "reasoning": f"Native trace {path.name} is present ({size} bytes).",
            "error": None,
            "details": {
                "bytes": size,
                "path": path.name,
                "unit": self.unit,
                "evidence": self.evidence,
            },
        }
