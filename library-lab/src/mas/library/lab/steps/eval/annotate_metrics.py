#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""AnnotateMetricsStep — pipeline step that appends metric scores to
``metrics/<metric_id>.jsonl``.

Storage layout::

    output/benchmark/
      trajectories.jsonl              ← input (from ExtractTrajectoriesStep)
      metrics/
        answer_relevancy.jsonl        ← appended by this step (idempotent)
        <other_metric>.jsonl          ← future metrics, separate files

Each ``metrics/<metric_id>.jsonl`` record::

    {
      "run_id":      str,    # join key with trajectories.jsonl
      "metric":      str,
      "level":       str,    # currently always "session"
      "score":       float,  # 0.0 – 1.0  (null on error)
      "reasoning":   str,
      "model":       str,
      "computed_at": str,
      "error":       str | null,
    }

Metrics are **expensive** (LLM calls).  This step runs session-level only by
default.  Expand to agent/call levels when budget allows.

Config keys::

    metric_class: str     fully-qualified class name  (default: AnswerRelevancyMetric)
    metric_kwargs: dict   keyword args forwarded to metric constructor
    level: str            scope to annotate (default: "session")
    max_items: int | null cap the number of records to annotate (default: null = all)
    overwrite: bool       re-annotate already-scored run_ids  (default: false)
"""

import importlib
import json
import logging
from pathlib import Path
from typing import Any

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


class AnnotateMetricsStep(PipelineStep):
    """Compute evaluation metrics on session-level trajectories.

    Reads ``trajectories.jsonl``, instantiates the configured ``EvalMetric``
    subclass, and appends new ``MetricRecord`` dicts to
    ``metrics/<metric_id>.jsonl``.  Already-scored run_ids are skipped.
    """

    type = "annotate_metrics"

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        bench_dir = ctx.output_dir
        traj_path = bench_dir / "trajectories.jsonl"

        if not traj_path.exists():
            logger.error("trajectories.jsonl not found at %s — run extract_trajectories first", bench_dir)
            return StepOutput(metadata={"annotated": 0, "skipped": 0, "errors": 0})

        # --- Instantiate metric ---
        metric = _load_metric(self.config)
        level = self.config.get("level", "session")
        max_items: int | None = self.config.get("max_items")
        overwrite = self.config.get("overwrite", False)

        # --- Locate output file ---
        metrics_dir = bench_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        out_path = metrics_dir / f"{metric.metric_id}.jsonl"

        # --- Load already-scored run_ids ---
        existing_ids: set[str] = set()
        existing_records: dict[str, dict] = {}  # run_id → record (for rewrite on retry)
        if out_path.exists() and not overwrite:
            for line in out_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        rec = json.loads(line)
                        rid = rec.get("run_id", "")
                        if rid:
                            existing_records[rid] = rec
                            # Only count as done if score was actually computed.
                            # Records with score=None (failed attempts) are retried.
                            if rec.get("score") is not None:
                                existing_ids.add(rid)
                    except json.JSONDecodeError:
                        logger.debug('suppressed', exc_info=True)

        # --- Load trajectories ---
        trajectories: list[dict[str, Any]] = []
        for line in traj_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    trajectories.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug('suppressed', exc_info=True)

        # Filter to runnable rows
        to_annotate = [
            t for t in trajectories
            if t.get("run_id") and t["run_id"] not in existing_ids
            and not t.get("_extraction_error")
        ]
        if max_items is not None:
            to_annotate = to_annotate[:max_items]

        logger.info(
            "Annotating %d/%d trajectories with %s (level=%s, skip=%d)",
            len(to_annotate), len(trajectories), metric.metric_id, level, len(existing_ids),
        )

        annotated = 0
        errors = 0
        # Collect newly computed records; will replace failed/missing entries
        new_records: dict[str, dict] = {}

        for rec in to_annotate:
            run_id = rec["run_id"]
            context = _build_context(rec, level)
            result = metric.compute(run_id=run_id, level=level, context=context)
            new_records[run_id] = result

            if result.get("error"):
                errors += 1
            else:
                annotated += 1

        if new_records:
            # Merge: keep fully-scored existing records, replace/add everything new
            retry_ids = set(new_records.keys())
            merged = {rid: r for rid, r in existing_records.items() if rid not in retry_ids}
            merged.update(new_records)
            # Also keep records for run_ids not involved in this pass
            with open(out_path, "w", encoding="utf-8") as out_f:
                for result in merged.values():
                    out_f.write(json.dumps(result, ensure_ascii=False) + "\n")

        logger.info(
            "AnnotateMetrics done: annotated=%d errors=%d skipped=%d → %s",
            annotated, errors, len(existing_ids), out_path,
        )

        # Write companion CSV via MetricFrame (pandas optional, stdlib csv fallback).
        try:
            from mas.lab.dataset.metric_frame import MetricFrame
            mf = MetricFrame.from_jsonl(out_path)
            csv_path = out_path.with_suffix(".csv")
            mf.to_csv(csv_path)
        except Exception as _mf_exc:
            logger.debug("MetricFrame CSV write skipped: %s", _mf_exc)

        return StepOutput(
            data={"metrics_path": str(out_path), "metric": metric.metric_id},
            files=[out_path],
            metadata={"annotated": annotated, "skipped": len(existing_ids), "errors": errors},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_METRIC_CLASS = "mas.lab.components.evaluation.deepeval_wrapper.AnswerRelevancyMetric"


def _load_metric(config: dict[str, Any]) -> Any:
    """Instantiate an EvalMetric from config dict."""
    class_path = config.get("metric_class", _DEFAULT_METRIC_CLASS)
    kwargs = config.get("metric_kwargs", {}) or {}

    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**kwargs)


def _build_context(trajectory: dict[str, Any], level: str) -> dict[str, Any]:
    """Extract the (input, output) context for a given level."""
    if level == "session":
        session = trajectory.get("session", {})
        return {
            # Use `or` so an empty string also falls back to the raw prompt
            "input": session.get("input") or trajectory.get("prompt", ""),
            "output": session.get("output") or "",
        }
    if level.startswith("agent:"):
        agent_id = level.split(":", 1)[1]
        agent_data = trajectory.get("agents", {}).get(agent_id, {})
        return {
            "input": agent_data.get("first_user_message", ""),
            "output": agent_data.get("final_output", ""),
        }
    # Fallback — session
    session = trajectory.get("session", {})
    return {
        "input": session.get("input", ""),
        "output": session.get("output", ""),
    }
