#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MetricsToDataFrameStep — one run's metrics.json → tidy data.csv."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.run_artifacts import run_dir_from_ctx

logger = logging.getLogger(__name__)


def rows_from_run_metrics(
    run_dir: Path,
    *,
    scenario: str,
    test: str,
    run: str,
    metrics_filename: str = "metrics.json",
) -> List[Dict[str, Any]]:
    """One tidy row per session metric in this run folder."""
    identity = {
        "scenario": scenario,
        "item_id": test[4:] if test.startswith("item") else test,
        "run_idx": run[1:] if run.startswith("r") else run,
    }
    run_info: dict = {}
    ri_path = run_dir / "run_info.json"
    if ri_path.exists():
        try:
            run_info = json.loads(ri_path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("suppressed", exc_info=True)
    latency_s = run_info.get("elapsed_ms", 0) / 1000.0

    m_path = run_dir / metrics_filename
    if not m_path.exists():
        return []
    try:
        doc = json.loads(m_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Skipping %s: %s", m_path, exc)
        return []

    rows: List[Dict[str, Any]] = []
    for metric_id, entry in doc.get("session", {}).items():
        if not isinstance(entry, dict) or entry.get("value") is None:
            continue
        rows.append(
            {
                **identity,
                "metric": metric_id,
                "value": float(entry["value"]),
                "latency_s": latency_s,
                "model": run_info.get("model", ""),
                "status": run_info.get("status", ""),
            }
        )
    return rows


class MetricsToDataFrameStep(PipelineStep):
    """Convert one run's metrics.json into a tidy CSV in that run folder."""

    type = "metrics_to_dataframe"

    async def execute(self, ctx: Any) -> StepOutput:
        config = self.config
        run_dir = run_dir_from_ctx(ctx, config)
        if run_dir is None:
            raise RuntimeError(
                f"metrics_to_dataframe '{self.name}' needs run_dir "
                "(place this step in run.post)."
            )

        scenario = str(config.get("scenario") or "")
        test = str(config.get("test") or "")
        run = str(config.get("run") or "")
        rows = rows_from_run_metrics(
            run_dir,
            scenario=scenario,
            test=test,
            run=run,
            metrics_filename=str(config.get("metrics_filename", "metrics.json")),
        )

        output_path = Path(config.get("output", "data.csv"))
        if not output_path.is_absolute():
            output_path = run_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        import pandas as pd

        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)
        return StepOutput(
            data={"rows": len(rows), "csv_path": str(output_path), "df": df},
            files=[output_path],
            metadata={"output": str(output_path)},
        )
