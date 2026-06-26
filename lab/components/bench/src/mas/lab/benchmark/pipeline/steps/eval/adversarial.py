#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""EvalAdversarialStep — compute adversarial metrics for MAS necessity.

For every ``metrics.json`` found under ``runs_dir``, compute adversarial
detection metrics and merge them with existing metrics.

Adversarial metrics complement standard MCE by explicitly measuring MAS advantages:
- Semantic contradiction detection (mn10)
- Exhaustive combinatorial search (mn11)
- Independent verification (mn12)

This step works directly from metrics.json (no kg.json required), making it
suitable for lightweight OSS deployments without full KG normalization.

Configuration
-------------
runs_dir       str           Path to the scenario runs root.
dataset_path   str           Path to dataset JSON (optional, auto-detected).
metrics        list[str]     Adversarial metric IDs to compute.
                             Default: ["budget_contradiction_detected",
                             "search_completeness", "injected_error_detected"].
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

_DEFAULT_ADVERSARIAL_METRICS = [
    "budget_contradiction_detected",
    "search_completeness",
    "injected_error_detected",
]


class EvalAdversarialStep(PipelineStep):
    """Compute adversarial detection metrics for every run in a directory tree.

    Input: ``metrics.json`` files with MCE metrics + final_response
    Output: adversarial metrics merged into existing ``metrics.json``.
    
    This step should run AFTER EvalMceBatchStep so it can merge adversarial
    metrics with standard MCE metrics in the same file.
    
    Unlike the KG-based proprietary extension, this OSS version works directly
    from metrics.json, making it suitable for paper experiments without a full
    normalization pipeline.
    """

    type = "eval_adversarial"

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        self._ctx = ctx
        from mas.library.eval.evaluator import get_provider
        from mas.library.eval.mce.runner import build_metrics_document

        config = self.config

        # ── Resolve runs_dir — defaults to ctx.output_dir when absent ──
        runs_dir_raw: Optional[str] = config.get("runs_dir")
        runs_dir = Path(runs_dir_raw) if runs_dir_raw else self._ctx.output_dir
        if not runs_dir.exists():
            raise FileNotFoundError(f"EvalAdversarialBatchStep '{self.name}': {runs_dir} not found")

        # ── Config ────────────────────────────────────────────────────
        dataset_path_raw: Optional[str] = config.get("dataset_path")
        if dataset_path_raw:
            dataset_path = Path(dataset_path_raw)
            if not dataset_path.is_absolute() and ctx.pipeline.config_path:
                dataset_path = (ctx.pipeline.config_path.parent / dataset_path).resolve()
        else:
            dataset_path = None
        metric_names: List[str] = config.get("metrics") or _DEFAULT_ADVERSARIAL_METRICS
        use_cache: bool = bool(config.get("use_cache", True))
        overwrite: bool = bool(config.get("overwrite", False))
        max_workers: int = int(config.get("max_workers", 4))
        
        # LLM judge configuration
        llm_model: str = config.get("llm_model", "gpt-4o")
        api_key_env: str = config.get("api_key_env", "OPENAI_API_KEY")
        api_base: Optional[str] = config.get("api_base")

        # overwrite takes precedence over use_cache
        if overwrite:
            use_cache = False

        # ── Initialize adversarial provider ───────────────────────────
        try:
            provider = get_provider(
                "adversarial",
                dataset_path=dataset_path,
                llm_model=llm_model,
                api_key_env=api_key_env,
                api_base=api_base,
            )
        except (ImportError, RuntimeError) as exc:
            raise RuntimeError(
                f"EvalAdversarialBatchStep '{self.name}': AdversarialProvider not available. "
                f"Install mas.library.eval: {exc}"
            ) from exc

        # ── Discover runs (metrics.json) ──────────────────────────────
        # OSS approach: read directly from metrics.json (no KG needed)
        metrics_paths = sorted(runs_dir.glob("*/item*/r*/metrics.json"))
        if not metrics_paths:
            logger.warning("EvalAdversarialBatchStep '%s': no metrics.json found under %s", self.name, runs_dir)

        total = len(metrics_paths)
        computed = 0
        cached = 0
        skipped = 0
        errors = 0

        # ── Filter to adversarial items only ──────────────────────────
        # Only process mn10, mn11, mn12 (adversarial items)
        adversarial_items = {"mn10", "mn11", "mn12"}
        
        todo: list[Tuple[Path, List[str], Dict[str, Any], str]] = []  # (metrics_path, missing_metrics, existing_session, final_response)
        for metrics_path in metrics_paths:
            # Extract item_id from path: scenario/itemmn10/r1/metrics.json
            item_dir = metrics_path.parent.parent
            item_id = item_dir.name.replace("item", "") if item_dir.name.startswith("item") else item_dir.name
            
            # Skip non-adversarial items
            if item_id not in adversarial_items:
                continue
            
            # Read existing metrics to check cache and extract final_response
            try:
                existing_doc = json.loads(metrics_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to read %s: %s", metrics_path, exc)
                continue
                
            existing_session = existing_doc.get("session", {})
            
            # Extract final_response - try multiple locations
            final_response = None
            
            # 1. Try session context (if MCE stored it)
            for key in ["final_response", "response", "output"]:
                if key in existing_session:
                    final_response = existing_session[key]
                    break
            
            # 2. If not found, read from events.jsonl (OSS lightweight path)
            if not final_response:
                # Look for traces/events.jsonl or ../traces/events.jsonl
                events_path = None
                if (metrics_path.parent / "traces" / "events.jsonl").exists():
                    events_path = metrics_path.parent / "traces" / "events.jsonl"
                elif (metrics_path.parent / "events.jsonl").exists():
                    events_path = metrics_path.parent / "events.jsonl"
                
                if events_path:
                    try:
                        final_response = self._extract_response_from_events(events_path)
                    except Exception as exc:
                        logger.warning("Failed to extract response from %s: %s", events_path, exc)
            
            if not final_response:
                logger.warning("No final_response found in %s, skipping adversarial eval", metrics_path)
                continue

            if use_cache:
                # Find which metrics are missing
                missing = [m for m in metric_names if m not in existing_session]
                if not missing:
                    skipped += 1
                    cached += len(metric_names)
                    continue
                # Partial hit: compute only the missing metrics
                cached += len(metric_names) - len(missing)
                todo.append((metrics_path, missing, existing_session, final_response))
            elif not overwrite:
                # Check if adversarial metrics already exist
                if any(m in existing_session for m in metric_names):
                    skipped += 1
                    continue
                # Merge with existing
                todo.append((metrics_path, metric_names, existing_session, final_response))
            else:
                todo.append((metrics_path, metric_names, existing_session, final_response))

        # ── Process concurrently ──────────────────────────────────────
        if not todo:
            summary = {
                "total": total,
                "adversarial_runs": 0,
                "runs_computed": 0,
                "metrics_computed": 0,
                "metrics_cached": cached,
                "skipped": skipped,
                "errors": 0,
                "provider": "adversarial",
            }
            logger.info("EvalAdversarialBatchStep '%s': no adversarial items to process", self.name)
            return StepOutput(data=summary, files=[], metadata={"runs_dir": str(runs_dir), **summary})

        logger.info(
            "EvalAdversarialBatchStep '%s': runs_dir=%s, metrics=%s, cache=%s, todo=%d",
            self.name, runs_dir, metric_names, use_cache, len(todo),
        )

        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(max_workers)

        async def _process_one(
            metrics_path: Path,
            metrics_to_eval: List[str],
            existing_session: Dict[str, Any],
            final_response: str,
        ) -> Tuple[int, int]:
            item_dir = metrics_path.parent.parent
            item_id = item_dir.name.replace("item", "") if item_dir.name.startswith("item") else item_dir.name
            scenario = item_dir.parent.name  # Get scenario from parent of item dir

            async with semaphore:
                try:
                    # OSS approach: compute directly from final_response text
                    fn = functools.partial(
                        provider.compute_from_text,
                        final_response,
                        item_id,
                        metrics_to_eval,
                    )
                    new_scores = await loop.run_in_executor(None, fn)

                    # Merge with existing metrics (preserve standard MCE metrics)
                    merged_session = {**existing_session, **new_scores}

                    doc = build_metrics_document(
                        item_id=item_id,
                        scenario=scenario,
                        session_scores=merged_session,
                    )
                    metrics_path.write_text(
                        json.dumps(doc, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    logger.debug(
                        "Written %s (adversarial=%d, existing=%d)",
                        metrics_path, len(metrics_to_eval), len(existing_session),
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
                    logger.error("EvalAdversarialBatchStep: failed on %s — %s", metrics_path, exc)
                    return 0, 1

        if todo:
            results = await asyncio.gather(
                *[_process_one(mp, m, s, r) for mp, m, s, r in todo]
            )
            for c, e in results:
                computed += c
                errors += e

        summary = {
            "total": total,
            "adversarial_runs": len(todo),
            "runs_computed": len(todo) - errors,
            "metrics_computed": computed,
            "metrics_cached": cached,
            "skipped": skipped,
            "errors": errors,
            "provider": "adversarial",
        }
        logger.info("EvalAdversarialBatchStep '%s' done — %s", self.name, summary)

        return StepOutput(
            data=summary,
            files=[],
            metadata={"runs_dir": str(runs_dir), **summary},
        )

    def _extract_response_from_events(self, events_path: Path) -> Optional[str]:
        """Extract final response from events.jsonl (OSS lightweight path).

        Reads the event stream and finds the last execution_end event,
        extracting its output as the final response.

        Args:
            events_path: Path to events.jsonl file

        Returns:
            Final response text or None if not found
        """
        last_output = None
        event_count = 0
        execution_end_count = 0
        
        logger.debug("Reading events from %s", events_path)
        with events_path.open(encoding="utf-8") as f:
            for line in f:
                event_count += 1
                try:
                    event = json.loads(line.strip())
                    # Look for execution_end events (agent completion)
                    if event.get("kind") == "execution_end":
                        execution_end_count += 1
                        # The output is stored directly in the 'output' field
                        output_content = event.get("output")
                        if output_content:
                            last_output = output_content
                            logger.debug("Found execution_end with output (%d chars)", len(str(output_content)))
                except json.JSONDecodeError:
                    continue
        
        logger.debug("Processed %d events, found %d execution_end events", event_count, execution_end_count)
        return last_output
