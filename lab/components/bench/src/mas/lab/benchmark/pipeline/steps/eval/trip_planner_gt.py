#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""EvalTripPlannerGTStep — ground-truth evaluation for MAS necessity items.

Demonstrates MCE extensibility: computes ``key_facts_accuracy`` and
``claim_verification`` metrics from ``TripPlannerGTProvider``, then merges
them with existing MCE metrics in each ``metrics.json``.

This step is the direct analogue of ``eval_adversarial`` but for the
ground-truth evaluation layer (mn1–mn4 items with Copilot-generated ground
truths).  Run it AFTER ``eval_mce`` so it can complement standard metrics.

Configuration
-------------
runs_dir       str           Path to the scenario runs root.
dataset_path   str           Path to mas-necessity.yaml (required — must
                             have ground_truth populated for mn1–mn4).
metrics        list[str]     GT metric IDs to compute.
                             Default: ["key_facts_accuracy"].
use_cache      bool          Only compute missing metrics.  Default: true.
overwrite      bool          Force re-compute of ALL metrics.  Default: false.
max_workers    int           Concurrent runs.  Default: 4.
llm_model      str           Judge model.  Default: "azure/gpt-4o-mini".
api_key_env    str           Env var for API key.  Default: "OPENAI_API_KEY".
api_base       str           OpenAI-compatible endpoint.
"""

import asyncio
import functools
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput

logger = logging.getLogger(__name__)

_DEFAULT_GT_METRICS = ["key_facts_accuracy"]
_GT_APPLICABLE_ITEMS = {"mn1", "mn2", "mn3", "mn4"}
_CLAIM_VERIFICATION_ITEMS = {"mn3"}


class EvalTripPlannerGTStep(PipelineStep):
    """Compute ground-truth evaluation metrics for MAS necessity items (mn1–mn4).

    Mirrors EvalAdversarialStep but uses TripPlannerGTProvider, which scores
    responses against verified ground truths rather than free-form LLM judgment.

    Extending MCE with this provider illustrates the core pattern:
      1. Subclass EvalProvider (trip_planner_gt.py)
      2. Implement compute_from_text(response, item_id, metrics)
      3. Create a pipeline step that invokes it and merges into metrics.json
      4. Reference from experiment YAML with ``type: eval_trip_planner_gt``
    """

    type = "eval_trip_planner_gt"

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        self._ctx = ctx
        from mas.library.eval.evaluator import register_provider
        from mas.library.eval.mce.runner import build_metrics_document

        config = self.config

        # ── Resolve runs_dir ─────────────────────────────────────────
        runs_dir_raw: Optional[str] = config.get("runs_dir")
        runs_dir = Path(runs_dir_raw) if runs_dir_raw else self._ctx.output_dir
        if not runs_dir.exists():
            raise FileNotFoundError(f"EvalTripPlannerGTStep '{self.name}': {runs_dir} not found")

        # ── Config ────────────────────────────────────────────────────
        dataset_path_raw: Optional[str] = config.get("dataset_path")
        if not dataset_path_raw:
            raise ValueError(f"EvalTripPlannerGTStep '{self.name}': dataset_path is required")
        dataset_path = Path(dataset_path_raw)
        if not dataset_path.is_absolute() and ctx.pipeline.config_path:
            dataset_path = (ctx.pipeline.config_path.parent / dataset_path).resolve()

        metric_names: List[str] = config.get("metrics") or _DEFAULT_GT_METRICS
        use_cache: bool = bool(config.get("use_cache", True))
        overwrite: bool = bool(config.get("overwrite", False))
        max_workers: int = int(config.get("max_workers", 4))
        llm_model: str = config.get("llm_model", "azure/gpt-4o-mini")
        api_key_env: str = config.get("api_key_env", "OPENAI_API_KEY")
        api_base: Optional[str] = config.get("api_base")

        if overwrite:
            use_cache = False

        # ── Load provider from lab-local eval/ directory ──────────────
        # The provider lives in the experiment's own eval/ subdirectory so
        # that lab authors can extend MCE without modifying the core library.
        # Default: eval/trip_planner_gt.py relative to the experiment YAML.
        provider_module_rel: str = config.get("provider_module", "eval/trip_planner_gt.py")
        if not ctx.pipeline.config_path:
            raise ValueError(
                f"EvalTripPlannerGTStep '{self.name}': pipeline has no config_path; "
                "cannot resolve provider_module"
            )
        provider_module_path = (ctx.pipeline.config_path.parent / provider_module_rel).resolve()
        if not provider_module_path.exists():
            raise FileNotFoundError(
                f"EvalTripPlannerGTStep '{self.name}': provider_module not found: "
                f"{provider_module_path}"
            )
        spec = importlib.util.spec_from_file_location("_lab_trip_planner_gt", provider_module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        TripPlannerGTProvider = mod.TripPlannerGTProvider

        # Instantiate and register with the MCE wrapper so get_provider("trip_planner_gt")
        # works for the lifetime of this process — other steps/scripts can reuse it.
        provider = TripPlannerGTProvider(
            dataset_path=dataset_path,
            llm_model=llm_model,
            api_key_env=api_key_env,
            api_base=api_base,
        )
        register_provider("trip_planner_gt", provider)

        # ── Discover all metrics.json files ───────────────────────────
        all_metrics_paths = sorted(runs_dir.rglob("metrics.json"))
        total = len(all_metrics_paths)

        todo: List[Tuple[Path, List[str], Dict[str, Any], str]] = []
        skipped = 0
        cached = 0

        for metrics_path in all_metrics_paths:
            try:
                with metrics_path.open(encoding="utf-8") as f:
                    doc = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Cannot read %s: %s", metrics_path, exc)
                continue

            existing_session: Dict[str, Any] = doc.get("session", {})
            raw_item_id: str = doc.get("item_id", metrics_path.parent.parent.name)
            # Strip the "item" prefix added by the benchmark directory layout.
            item_id = raw_item_id[4:] if raw_item_id.startswith("item") and raw_item_id[4:] else raw_item_id

            # Only process items that have ground truths
            if item_id not in _GT_APPLICABLE_ITEMS:
                skipped += 1
                continue

            # Filter metric_names to applicable ones for this item
            applicable_metrics = list(metric_names)
            if "claim_verification" in applicable_metrics and item_id not in _CLAIM_VERIFICATION_ITEMS:
                applicable_metrics = [m for m in applicable_metrics if m != "claim_verification"]

            if not applicable_metrics:
                skipped += 1
                continue

            # Extract final_response
            final_response = self._extract_final_response(metrics_path, existing_session)
            if not final_response:
                logger.warning("No final_response found in %s, skipping GT eval", metrics_path)
                skipped += 1
                continue

            if use_cache:
                missing = [m for m in applicable_metrics if m not in existing_session]
                if not missing:
                    skipped += 1
                    cached += len(applicable_metrics)
                    continue
                cached += len(applicable_metrics) - len(missing)
                todo.append((metrics_path, missing, existing_session, final_response))
            else:
                todo.append((metrics_path, applicable_metrics, existing_session, final_response))

        if not todo:
            summary = {
                "total": total,
                "runs_computed": 0,
                "metrics_computed": 0,
                "metrics_cached": cached,
                "skipped": skipped,
                "errors": 0,
                "provider": "trip_planner_gt",
            }
            return StepOutput(data=summary, files=[], metadata={"runs_dir": str(runs_dir), **summary})

        logger.info(
            "EvalTripPlannerGTStep '%s': runs_dir=%s, metrics=%s, cache=%s, todo=%d",
            self.name, runs_dir, metric_names, use_cache, len(todo),
        )

        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(max_workers)
        errors = 0
        metrics_computed = 0

        async def _process_one(
            metrics_path: Path,
            metrics_to_eval: List[str],
            existing_session: Dict[str, Any],
            final_response: str,
        ) -> Tuple[int, int]:
            nonlocal errors, metrics_computed
            item_dir = metrics_path.parent.parent
            item_id = item_dir.name
            scenario = item_dir.parent.name

            async with semaphore:
                try:
                    fn = functools.partial(
                        provider.compute_from_text,
                        final_response,
                        item_id,
                        metrics_to_eval,
                    )
                    new_scores = await loop.run_in_executor(None, fn)

                    merged_session = {**existing_session, **new_scores}
                    doc = build_metrics_document(
                        item_id=item_id,
                        scenario=scenario,
                        session_scores=merged_session,
                    )
                    with metrics_path.open("w", encoding="utf-8") as f:
                        json.dump(doc, f, indent=2)

                    metrics_computed += len(metrics_to_eval)
                    return 1, len(metrics_to_eval)
                except Exception as exc:
                    logger.error("GT eval failed for %s: %s", metrics_path, exc)
                    errors += 1
                    return 0, 0

        await asyncio.gather(*[_process_one(*args) for args in todo])

        summary = {
            "total": total,
            "runs_computed": len(todo),
            "metrics_computed": metrics_computed,
            "metrics_cached": cached,
            "skipped": skipped,
            "errors": errors,
            "provider": "trip_planner_gt",
        }
        return StepOutput(data=summary, files=[], metadata={"runs_dir": str(runs_dir), **summary})

    def _extract_final_response(
        self, metrics_path: Path, existing_session: Dict[str, Any]
    ) -> Optional[str]:
        """Extract the agent's final response from metrics.json or nearby events."""
        for key in ("final_response", "response", "output"):
            if key in existing_session:
                return str(existing_session[key])

        # Resolve events.jsonl: check the run dir first, then the trace-cache
        # (benchmark stores traces in the content-addressed cache, linked via .run_ref).
        run_dir = metrics_path.parent
        candidates: list[Path] = [
            run_dir / "traces" / "events.jsonl",
            run_dir / "events.jsonl",
        ]

        # Follow .run_ref → trace-cache/<hash>/traces/events.jsonl
        run_ref = run_dir / ".run_ref"
        if run_ref.exists():
            try:
                from mas.lab.paths import trace_cache as _trace_cache
                run_hash = run_ref.read_text(encoding="utf-8").strip()
                candidates.append(_trace_cache() / run_hash / "traces" / "events.jsonl")
            except Exception:
                logger.debug('suppressed', exc_info=True)

        for candidate in candidates:
            if candidate.exists():
                try:
                    return self._extract_response_from_events(candidate)
                except Exception as exc:
                    logger.warning("Failed to extract response from %s: %s", candidate, exc)
        return None

    def _extract_response_from_events(self, events_path: Path) -> Optional[str]:
        """Extract the final agent output from an events.jsonl file.

        Supports two event formats:
        - Legacy: ``type == "agent_response"`` or ``role == "assistant"``
        - Runtime: ``kind == "execution_end"`` with ``output`` field.
          Prefers the root execution (``parent_call_id`` is null/absent).
        """
        last_response = None
        root_response = None
        with events_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Legacy format
                if event.get("type") == "agent_response" or (
                    event.get("role") == "assistant" and event.get("content")
                ):
                    content = event.get("content") or event.get("response", "")
                    if content:
                        last_response = str(content)
                # Runtime format — execution_end with output
                elif event.get("kind") == "execution_end":
                    output = event.get("output")
                    if output:
                        last_response = str(output)
                        if not event.get("parent_call_id"):
                            # Root execution — this is the MAS final answer
                            root_response = str(output)
        return root_response or last_response
