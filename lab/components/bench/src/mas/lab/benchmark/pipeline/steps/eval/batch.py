#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""EvalBatchStep — compute quality metrics for all runs from their KG.

For every ``item*/r*/kg.json`` found under ``runs_dir``, compute the
requested metrics via the generic evaluation module and write a standalone
``metrics.json`` artefact next to ``run_info.json``.

Uses :func:`mas.library.eval.evaluator.evaluate_run` with an explicit ``provider``.

Configuration
-------------
runs_dir       str           Path to the scenario runs root.
response_agent str           Override root agent detection.  Default: auto.
metrics        list[str]     Metric IDs to compute.
                             Default: ["GoalSuccessRate", "Groundedness",
                             "AnswerRelevancy", "ResponseCompleteness"].
provider       str           Evaluation provider (required): "mce", "mce_oss", etc.
use_cache      bool          Enable metric-level cache.  When true, existing
                             metrics.json is inspected per-metric: only
                             *missing* metrics are computed, existing ones
                             are preserved.  Default: true.
overwrite      bool          Force re-compute of ALL metrics regardless of
                             cache.  Default: false.  Takes precedence over
                             ``use_cache``.
max_workers    int           Concurrent runs.  Default: 4.
"""

import asyncio
import functools
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput

logger = logging.getLogger(__name__)

_DEFAULT_METRICS = [
    "goal_success_rate",
    "groundedness",
    "answer_relevancy",
    "response_completeness",
]


class EvalBatchStep(PipelineStep):
    """Compute quality metrics for every run in a directory tree.

    Input: ``kg.json`` knowledge graphs (output of normalize_events).
    Output: ``metrics.json`` artefacts placed next to ``run_info.json``.
    """

    type = "eval_batch"

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        from mas.library.eval.evaluator import evaluate_run, get_provider, list_available_providers
        from mas.library.eval.mce.runner import build_metrics_document

        config = self.config

        # ── Resolve runs_dir ──────────────────────────────────────────
        runs_dir_raw: Optional[str] = config.get("runs_dir")
        if not runs_dir_raw:
            raise ValueError(f"EvalBatchStep '{self.name}': 'runs_dir' required")
        runs_dir = Path(runs_dir_raw)
        if not runs_dir.exists():
            raise FileNotFoundError(f"EvalBatchStep '{self.name}': {runs_dir} not found")

        # ── Config ────────────────────────────────────────────────────
        response_agent: Optional[str] = config.get("response_agent") or None
        metric_names: List[str] = config.get("metrics") or _DEFAULT_METRICS
        provider_name: Optional[str] = config.get("provider")
        if not provider_name:
            available = list_available_providers()
            raise ValueError(
                f"EvalBatchStep '{self.name}': 'provider' is required (no auto-fallback). "
                f"Available providers: {', '.join(available) or '(none)'}"
            )
        use_cache: bool = bool(config.get("use_cache", True))
        overwrite: bool = bool(config.get("overwrite", False))
        max_workers: int = int(config.get("max_workers", 4))

        # overwrite takes precedence over use_cache
        if overwrite:
            use_cache = False

        # ── Discover runs (kg.json) ──────────────────────────────────
        kg_paths = sorted(runs_dir.glob("item*/r*/kg.json"))
        if not kg_paths:
            logger.warning("EvalBatchStep '%s': no kg.json found under %s", self.name, runs_dir)

        total = len(kg_paths)
        computed = 0
        cached = 0
        skipped = 0
        errors = 0

        # ── Determine work per run ────────────────────────────────────
        todo: list[Tuple[Path, List[str], Dict[str, Any]]] = []  # (kg_path, metrics_to_compute, existing_session)
        for kg_path in kg_paths:
            metrics_file = kg_path.parent / "metrics.json"

            if use_cache and metrics_file.exists():
                try:
                    existing_doc = json.loads(metrics_file.read_text(encoding="utf-8"))
                except Exception:
                    existing_doc = {}
                existing_session = existing_doc.get("session", {})

                # Find which metrics are missing
                missing = [m for m in metric_names if m not in existing_session]
                if not missing:
                    skipped += 1
                    cached += len(metric_names)
                    continue
                # Partial hit: compute only the missing metrics
                cached += len(metric_names) - len(missing)
                todo.append((kg_path, missing, existing_session))
            elif not overwrite and metrics_file.exists():
                # Legacy behavior: skip entirely if file exists
                skipped += 1
                continue
            else:
                todo.append((kg_path, metric_names, {}))

        # ── Process concurrently ──────────────────────────────────────
        # Defer provider validation until we know there's actual work.
        # When all metrics are cached, no provider is needed.
        if not todo:
            summary = {
                "total": total,
                "runs_computed": 0,
                "metrics_computed": 0,
                "metrics_cached": cached,
                "skipped": skipped,
                "errors": 0,
                "provider": "(all cached)",
            }
            logger.info("EvalBatchStep '%s': all metrics cached — nothing to evaluate", self.name)
            return StepOutput(data=summary, files=[], metadata={"runs_dir": str(runs_dir), **summary})

        provider = get_provider(provider_name)
        logger.info(
            "EvalBatchStep '%s': provider=%s, runs_dir=%s, metrics=%s, cache=%s, todo=%d",
            self.name, provider.name, runs_dir, metric_names, use_cache, len(todo),
        )

        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(max_workers)

        async def _process_one(
            kg_path: Path,
            metrics_to_eval: List[str],
            existing_session: Dict[str, Any],
        ) -> Tuple[int, int]:
            run_folder = kg_path.parent
            metrics_file = run_folder / "metrics.json"
            item_dir = run_folder.parent
            item_id = item_dir.name.replace("item", "") if item_dir.name.startswith("item") else item_dir.name
            scenario = runs_dir.name

            async with semaphore:
                try:
                    fn = functools.partial(
                        evaluate_run,
                        kg_path,
                        metrics_to_eval,
                        provider=provider_name,
                        response_agent_id=response_agent,
                    )
                    new_scores = await loop.run_in_executor(None, fn)

                    # Merge with cached metrics
                    merged_session = {**existing_session, **new_scores}

                    doc = build_metrics_document(
                        item_id=item_id,
                        scenario=scenario,
                        session_scores=merged_session,
                    )
                    metrics_file.write_text(
                        json.dumps(doc, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    logger.debug(
                        "Written %s (computed=%d, cached=%d)",
                        metrics_file, len(metrics_to_eval), len(existing_session),
                    )
                    return len(metrics_to_eval), 0
                except Exception as exc:
                    # Authentication errors (bad/missing API key) are fatal — re-raise
                    # so the pipeline step fails instead of silently recording zeros.
                    _err = str(exc)
                    if (
                        "AuthenticationError" in type(exc).__name__
                        or "Incorrect API key" in _err
                        or "invalid_api_key" in _err
                        or "is not set" in _err
                        or ("401" in _err and "api" in _err.lower())
                    ):
                        raise
                    logger.error("EvalBatchStep: failed on %s — %s", kg_path, exc)
                    return 0, 1

        if todo:
            results = await asyncio.gather(
                *[_process_one(kg, m, s) for kg, m, s in todo]
            )
            for c, e in results:
                computed += c
                errors += e

        summary = {
            "total": total,
            "runs_computed": len(todo) - errors,
            "metrics_computed": computed,
            "metrics_cached": cached,
            "skipped": skipped,
            "errors": errors,
            "provider": provider.name,
        }
        logger.info("EvalBatchStep '%s' done — %s", self.name, summary)

        return StepOutput(
            data=summary,
            files=[],
            metadata={"runs_dir": str(runs_dir), **summary},
        )
