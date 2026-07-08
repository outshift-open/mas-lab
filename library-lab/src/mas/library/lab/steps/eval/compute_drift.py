#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""ComputeDriftStep — compute semantic drift from embeddings.

Implements note 09 §4.1:
    drift = 1 - cos_sim(embed(input), embed(output))

Reads embedding JSONL files produced by EmbedStep, pairs input/output vectors
by run_id, computes cosine similarity, and writes per-run drift values.

Output::

    {output_dir}/metrics/drift.jsonl

Each record::

    {
      "run_id":  str,
      "level":   str,        # "session" | "agent:<id>"
      "drift":   float,      # 1 - cos_sim ∈ [0, 2], typically [0, 1]
      "cos_sim": float,      # raw cosine similarity ∈ [-1, 1]
    }

Config keys::

    level: str         which level to compute drift for (default: "session")

The step also injects drift into each run's ``metrics.json`` under the
``session`` key so that ``collect_metrics`` can pick it up alongside MCE
metrics.
"""

import json
import logging
import math
from pathlib import Path
from typing import Any

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class ComputeDriftStep(PipelineStep):
    """Compute semantic drift = 1 - cos_sim(embed(input), embed(output))."""

    type = "compute_drift"

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        bench_dir = ctx.output_dir
        level = self.config.get("level", "session")
        level_key = level.replace(":", "__")

        embeddings_dir = bench_dir / "embeddings"
        input_path = embeddings_dir / f"{level_key}__input.jsonl"
        output_path = embeddings_dir / f"{level_key}__output.jsonl"

        if not input_path.exists() or not output_path.exists():
            logger.error(
                "ComputeDrift: embedding files not found (%s, %s) — run embed_trajectories first",
                input_path, output_path,
            )
            return StepOutput(metadata={"computed": 0})

        # Load embeddings keyed by run_id
        input_vecs: dict[str, list[float]] = {}
        for line in input_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                input_vecs[rec["run_id"]] = rec["vector"]

        output_vecs: dict[str, list[float]] = {}
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                output_vecs[rec["run_id"]] = rec["vector"]

        # Compute drift for paired run_ids
        common_ids = sorted(set(input_vecs) & set(output_vecs))
        if not common_ids:
            logger.warning("ComputeDrift: no paired embeddings found for level=%s", level)
            return StepOutput(metadata={"computed": 0})

        metrics_dir = bench_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        drift_path = metrics_dir / "drift.jsonl"

        records: list[dict[str, Any]] = []
        for run_id in common_ids:
            cos_sim = _cosine_similarity(input_vecs[run_id], output_vecs[run_id])
            drift = 1.0 - cos_sim
            records.append({
                "run_id": run_id,
                "level": level,
                "drift": round(drift, 6),
                "cos_sim": round(cos_sim, 6),
            })

        with open(drift_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # Inject drift into per-run metrics.json for collect_metrics compatibility
        _inject_into_run_metrics(bench_dir, records)

        logger.info(
            "ComputeDrift done: %d runs, mean_drift=%.4f",
            len(records),
            sum(r["drift"] for r in records) / len(records) if records else 0,
        )
        return StepOutput(
            data={"drift_path": str(drift_path)},
            files=[drift_path],
            metadata={"computed": len(records)},
        )


def _inject_into_run_metrics(bench_dir: Path, drift_records: list[dict[str, Any]]) -> None:
    """Write drift values into each run's metrics.json.

    This ensures collect_metrics can pick up drift alongside MCE metrics
    when reading metrics.json per run.
    """
    drift_by_run = {r["run_id"]: r for r in drift_records}

    # Discover run directories: item*/r*/metrics.json
    for metrics_file in sorted(bench_dir.glob("item*/r*/metrics.json")):
        run_dir = metrics_file.parent
        # Match run_id from run_info.json
        run_info_path = run_dir / "run_info.json"
        if not run_info_path.exists():
            continue
        try:
            run_info = json.loads(run_info_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        run_id = run_info.get("run_id", "")
        if run_id not in drift_by_run:
            continue

        # Merge drift into metrics.json
        try:
            doc = json.loads(metrics_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            doc = {}

        session = doc.setdefault("session", {})
        session["semantic_drift"] = {
            "value": drift_by_run[run_id]["drift"],
            "reasoning": f"1 - cos_sim(embed(input), embed(output)) = {drift_by_run[run_id]['drift']:.4f}",
            "error": None,
        }
        metrics_file.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
