#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""EvalMceStep \u2014 MCE session metrics for all runs in a directory tree.

For every ``item*/r*/traces/events.jsonl`` found under ``runs_dir``,
compute all (or a subset of) MCE LLM-as-judge session metrics and write
a standalone ``item*/r*/metrics.json`` artefact in place.

``metrics.json`` is intentionally placed **next to** ``run_info.json``
(not in the pipeline\u2019s output directory) so it travels with
the run and is available to downstream analysis scripts.

Configuration
-------------
runs_dir       str           Path to the runs root
                             (e.g. ``output/01-semantic-grouping/baseline/``).
                             Relative paths are resolved from the pipeline
                             YAML\u2019s directory.
response_agent str           agent_id whose last ``execution_end`` is the
                             final session response.
                             Default: ``null`` — auto-detected from the trace
                             (root ``execution_start`` agent_id).
metrics        list[str]     MCE metric ids to compute.
                             Default: all session-level metrics from METRIC_MAP
                             (goal_success_rate, groundedness,
                             response_completeness, workflow_cohesion_index,
                             workflow_efficiency, consistency,
                             context_preservation, information_retention,
                             intent_recognition_accuracy,
                             component_conflict_rate).
overwrite      bool          Re-compute runs that already have metrics.json.
                             Default: ``false``.
validate       bool          Validate each metrics.json against its JSON
                             schema before writing.  Default: ``true``.
max_workers    int           Concurrent evaluation threads.  Default: 2.
                              Keep low when using a rate-limited eval LLM proxy.
                              Higher values amplify burst pressure even with
                              retry backoff in the MCE runner.
fail_threshold float         Fraction of items that may fail before the step
                             raises ``StepError``.  0.0 = any failure raises;
                             1.0 = never raise (default for backward compat).
                             Recommended lab value: 0.5.

Step output
-----------
data:
  total          int   Runs discovered.
  computed       int   metrics.json files written.
  skipped        int   Runs skipped (metrics.json exists + overwrite=false).
  errors         int   Runs that failed.
files:
  (none \u2014 artefacts are written in-place next to run_info.json)
"""

import asyncio
import functools
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


class EvalMceStep(PipelineStep):
    """Compute MCE session metrics for every run in a directory tree.

    Writes a standalone ``metrics.json`` artefact per run folder.
    """

    type = "eval_mce"
    persistent = True  # LLM-as-judge calls are expensive; persist output to avoid re-running

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        from mas.library.eval.mce.runner import (
            ALL_SESSION_METRICS,
            build_metrics_document,
            compute_session_metrics,
            install_openai_llm_service,
        )

        config = self.config

        # ----------------------------------------------------------------
        # Resolve runs_dir — defaults to ctx.output_dir when absent
        # ----------------------------------------------------------------
        runs_dir_raw: Optional[str] = config.get("runs_dir")
        if runs_dir_raw:
            runs_dir = Path(runs_dir_raw)
            if not runs_dir.is_absolute() and ctx.pipeline.config_path:
                runs_dir = (ctx.pipeline.config_path.parent / runs_dir).resolve()
        else:
            runs_dir = ctx.output_dir

        if not runs_dir.exists():
            raise FileNotFoundError(
                f"EvalMceStep '{self.name}': runs_dir not found: {runs_dir}"
            )

        # ----------------------------------------------------------------
        # Config
        # ----------------------------------------------------------------
        response_agent: Optional[str] = config.get("response_agent") or None
        metric_names: List[str] = config.get("metrics") or ALL_SESSION_METRICS
        overwrite: bool = bool(config.get("overwrite", False))
        do_validate: bool = bool(config.get("validate", True))
        max_workers: int = int(config.get("max_workers", 2))
        fail_threshold: float = float(config.get("fail_threshold", 1.0))
        model_override: Optional[str] = config.get("model") or None
        metrics_filename: str = config.get("metrics_filename", "metrics.json")

        # ----------------------------------------------------------------
        # Install MCE LLM service (once per process)
        # ----------------------------------------------------------------
        if model_override:
            # Force re-install with the requested judge model so Lab 4.A can
            # re-evaluate the same traces under multiple judges.
            install_openai_llm_service(model_override=model_override)
        else:
            install_openai_llm_service()

        # ----------------------------------------------------------------
        # Load JSON schema for validation
        # ----------------------------------------------------------------
        schema = _load_metrics_schema() if do_validate else None

        # ----------------------------------------------------------------
        # Discover runs (recursive: works both with per-scenario runs_dir and
        # with the experiment output root containing multiple scenario dirs).
        # Uses os.walk(followlinks=True) so symlinked traces/ directories
        # (content-addressed run cache) are always discovered.
        # ----------------------------------------------------------------
        trace_paths = _find_traces(runs_dir)
        if not trace_paths:
            logger.warning(
                "EvalMceStep '%s': no traces found under %s", self.name, runs_dir
            )

        total    = len(trace_paths)
        computed = 0
        skipped  = 0
        errors   = 0
        warnings_count = 0

        logger.info(
            "EvalMceStep '%s': %d runs in %s — metrics: %s (max_workers=%d)",
            self.name, total, runs_dir, metric_names, max_workers,
        )

        # ------------------------------------------------------------------
        # Split into already-done (skip) vs to-compute
        # ------------------------------------------------------------------
        todo: List[Path] = []
        for trace_path in trace_paths:
            metrics_file = trace_path.parent.parent / metrics_filename
            if metrics_file.exists() and not overwrite:
                skipped += 1
            else:
                todo.append(trace_path)

        # ------------------------------------------------------------------
        # Process pending runs concurrently via ThreadPoolExecutor
        # compute_session_metrics is synchronous (LLM HTTP calls) so we
        # offload each run to a thread and gather results with a semaphore.
        # ------------------------------------------------------------------
        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(max_workers)

        async def _process_one(trace_path: Path) -> Tuple[int, int, int]:  # (computed, errors, warnings)
            run_folder = trace_path.parent.parent
            metrics_file = run_folder / metrics_filename
            try:
                item_dir  = run_folder.parent
                rel_parts = run_folder.relative_to(runs_dir).parts
                # Nested layout: {scenario}/item{id}/r{N}  → rel_parts has ≥3 parts
                # Flat layout:   item{id}/r{N}             → rel_parts has 2 parts
                if len(rel_parts) >= 3:
                    scenario    = rel_parts[0]
                    item_id_raw = rel_parts[1]
                else:
                    scenario    = runs_dir.name
                    item_id_raw = item_dir.name
                item_id = item_id_raw.replace("item", "") if item_id_raw.startswith("item") else item_id_raw
            except Exception:
                item_id  = run_folder.parent.name
                scenario = runs_dir.name

            async with semaphore:
                try:
                    fn = functools.partial(
                        compute_session_metrics,
                        trace_path,
                        metric_names,
                        response_agent_id=response_agent,
                    )
                    session_scores = await loop.run_in_executor(None, fn)
                    doc = build_metrics_document(
                        item_id=item_id,
                        scenario=scenario,
                        session_scores=session_scores,
                    )
                    if schema is not None:
                        _validate_document(doc, schema, trace_path)
                    # Embed run_hash + cache_key AFTER schema validation —
                    # these are pipeline-internal fields not declared in the schema.
                    # collect_metrics reads them from the file directly.
                    run_ref_f = run_folder / ".run_ref"
                    if run_ref_f.exists():
                        try:
                            _run_hash = run_ref_f.read_text(encoding="utf-8").strip()
                            doc["run_hash"] = _run_hash
                            # cache_key is the same as run_hash when computed by
                            # the MAS runner (single-manifest, single-overlay path).
                            # Unified cache keys (multi-overlay) stored separately.
                            doc["cache_key"] = _run_hash
                        except Exception:
                            logger.debug('suppressed', exc_info=True)
                    metrics_file.write_text(
                        json.dumps(doc, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    logger.debug("Written %s", metrics_file)
                    has_warning = bool(doc.get("run_quality", {}).get("warnings"))
                    return 1, 0, (1 if has_warning else 0)
                except Exception as exc:
                    logger.error("EvalMceStep: failed on %s — %s", trace_path, exc)
                    return 0, 1, 0

        if todo:
            results = await asyncio.gather(*[_process_one(p) for p in todo])
            for c, e, w in results:
                computed += c
                errors   += e
                warnings_count += w

        summary = {
            "total":    total,
            "computed": computed,
            "skipped":  skipped,
            "errors":   errors,
            "warnings": warnings_count,
        }
        logger.info(
            "EvalMceStep '%s' done — %s", self.name, summary
        )

        # Surface errors visibly in the step metadata so the pipeline
        # progress line can show [computed=X, skipped=Y, errors=Z].
        if errors > 0:
            err_rate = errors / max(total - skipped, 1)
            if err_rate > fail_threshold:
                raise RuntimeError(
                    f"EvalMceStep '{self.name}': {errors}/{total - skipped} items failed "
                    f"({err_rate:.0%} > fail_threshold={fail_threshold:.0%}). "
                    "Re-run to retry failed items (overwrite=false skips completed ones)."
                )
            else:
                logger.warning(
                    "EvalMceStep '%s': %d/%d items failed evaluation — "
                    "re-run to retry (overwrite=false will skip completed items)",
                    self.name, errors, total - skipped,
                )

        return StepOutput(
            data=summary,
            files=[],
            metadata={
                "runs_dir": str(runs_dir),
                "summary": f"computed={computed}, skipped={skipped}, errors={errors}, warnings={warnings_count}",
                **summary,
            },
        )

    def outputs_exist(self, output_dir: Path) -> bool:
        """Caching not supported for batch steps (always re-check via overwrite flag)."""
        return False


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_metrics_schema() -> Optional[Dict[str, Any]]:
    """Load the JSON schema for metrics.json artefacts."""
    from mas.lab.schemas.paths import lab_artefact_schema_dir

    schema_path = lab_artefact_schema_dir() / "metrics.schema.json"
    if not schema_path.exists():
        logger.debug("metrics.schema.json not found at %s — skipping validation", schema_path)
        return None
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load metrics schema: %s", exc)
        return None


def _validate_document(doc: Dict[str, Any], schema: Dict[str, Any], trace_path: Path) -> None:
    """Validate *doc* against *schema* using jsonschema (soft failure)."""
    try:
        import jsonschema
        jsonschema.validate(doc, schema)
    except ImportError:
        logger.debug("jsonschema not installed — skipping metrics validation")
    except Exception as exc:
        logger.warning("metrics.json validation failed for %s: %s", trace_path, exc)


def _find_traces(runs_dir: Path) -> List[Path]:
    """Walk *runs_dir* following symlinks and return all ``events.jsonl`` paths.

    Uses ``os.walk(followlinks=True)`` instead of ``Path.glob()`` so that
    symlinked ``traces/`` directories (content-addressed run cache) are always
    discovered regardless of Python version or OS.

    Only paths matching the ``item*/r*/traces/events.jsonl`` convention are
    returned.
    """
    result: List[Path] = []
    for root, _dirs, files in os.walk(runs_dir, followlinks=True):
        p = Path(root)
        if p.name == "traces" and "events.jsonl" in files:
            # Validate the expected layout: …/item*/r*/traces/events.jsonl
            try:
                rel = p.relative_to(runs_dir)
                parts = rel.parts  # e.g. ("scenario", "itemX", "r1", "traces")
                # Accept both nested (4 parts) and flat (3 parts) layouts.
                run_dir = p.parent
                item_dir = run_dir.parent
                if item_dir.name.startswith("item") or run_dir.parent.name.startswith("item"):
                    result.append(p / "events.jsonl")
            except ValueError:
                logger.debug('suppressed', exc_info=True)
    return sorted(result)
