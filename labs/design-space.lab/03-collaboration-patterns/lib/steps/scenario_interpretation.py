#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Build a scenario interpretation table for collaboration-pattern experiments.

Input: collect_metrics CSV-like data with at least a `scenario` column.
Output: one-row-per-scenario table with parsed axes (topology, moderator_pattern).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput, register_step_type


def _parse_topology(scenario: str) -> str:
    return "parallel" if "parallel" in scenario else "moderator-broker"


def _parse_pattern(scenario: str) -> str:
    if "react" in scenario:
        return "react"
    if "cot" in scenario:
        return "cot"
    if "reflection" in scenario:
        return "reflection"
    return "unknown"


class ScenarioInterpretationStep(PipelineStep):
    type = "scenario_interpretation"

    async def execute(self, ctx) -> StepOutput:
        source = self.config.get("data", "@collect-metrics")
        if isinstance(source, str) and source.startswith("@"):
            data = ctx.step_output(source[1:]).data
        else:
            data = source

        if isinstance(data, str):
            df = pd.read_csv(data)
        elif isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            df = pd.DataFrame(data)

        configured = self.config.get("scenarios") or []
        if "scenario" in df.columns:
            scenarios = sorted(df["scenario"].dropna().astype(str).unique())
        else:
            scenarios = []
        if not scenarios:
            scenarios = [str(s) for s in configured if str(s).strip()]
        if not scenarios:
            raise ValueError("scenario_interpretation requires scenario data or config.scenarios")

        out = pd.DataFrame({"scenario": scenarios})
        out["topology"] = out["scenario"].map(_parse_topology)
        out["moderator_pattern"] = out["scenario"].map(_parse_pattern)

        output_cfg = str(self.config.get("output", "{output_dir}/results/scenario_interpretation.csv"))
        output = Path(output_cfg.replace("{output_dir}", str(ctx.output_dir)))
        output.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(output, index=False)

        return StepOutput(data=out, files=[output], metadata={"output": str(output)})


register_step_type("scenario_interpretation", ScenarioInterpretationStep)
