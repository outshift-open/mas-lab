#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""EvalMceStep — score one run's events.jsonl into metrics.json."""
from __future__ import annotations

import asyncio
import functools
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext
from mas.lab.benchmark.pipeline.models import ConfigParam
from mas.lab.benchmark.pipeline.run_artifacts import resolve_run_events, run_dir_from_ctx

logger = logging.getLogger(__name__)

# Many run-scoped instances can score in parallel; this caps judge HTTP calls.
_JUDGE_SEMAPHORES: Dict[int, asyncio.Semaphore] = {}


def _judge_semaphore(max_workers: int) -> asyncio.Semaphore:
    sem = _JUDGE_SEMAPHORES.get(max_workers)
    if sem is None:
        sem = asyncio.Semaphore(max_workers)
        _JUDGE_SEMAPHORES[max_workers] = sem
    return sem


def _install_judge(config: dict[str, Any], ctx: ExecutionContext) -> tuple[str, str]:
    from mas.library.eval.mce.judge_model import resolve_judge_model
    from mas.library.eval.mce.runner import install_openai_llm_service

    backfilled = config.get("model_source") if config.get("model") else None
    step_model = config.get("model")
    evaluation_model = None
    judge_metadata: Optional[Dict[str, Any]] = None
    if backfilled:
        step_model = None
        if str(backfilled).startswith("experiment.evaluation"):
            evaluation_model = config.get("model")
        elif str(backfilled).startswith("experiment.metadata"):
            judge_metadata = {"model_name": config.get("model")}
    judged = resolve_judge_model(
        step_model=step_model,
        step_judge_model=config.get("judge_model"),
        evaluation_model=evaluation_model,
        metadata=judge_metadata,
        template_vars=getattr(ctx, "template_vars", None),
    )
    effective = install_openai_llm_service(
        model_override=judged.model, model_source=judged.source
    )
    logger.info(
        "EvalMceStep judge model=%s source=%s",
        effective or judged.model or "(infra default)",
        judged.source,
    )
    return effective or judged.model or "", judged.source


class EvalMceStep(PipelineStep):
    """Score ``traces/events.jsonl`` and write ``metrics.json`` in that run folder."""

    type = "eval_mce"
    persistent = True

    PARAMS = [
        ConfigParam("runs_dir", str, default=None,
                    description="Runs tree containing item*/r*/traces/events.jsonl."),
        ConfigParam("response_agent", str, default=None,
                    description="agent_id whose last execution_end is the session answer."),
        ConfigParam("metrics", list, default=None,
                    description="MCE session metric ids. Default: all session metrics."),
        ConfigParam("overwrite", bool, default=False,
                    description="Recompute existing metrics.json."),
        ConfigParam("validate", bool, default=True,
                    description="Validate metrics.json against schema."),
        ConfigParam("max_workers", int, default=2,
                    description="Parallel judge threads."),
        ConfigParam("fail_threshold", float, default=1.0,
                    description="Fraction of items that may fail before the step raises."),
        ConfigParam("model", str, default=None,
                    description="LLM-as-judge model. Default: experiment.evaluation.model, "
                                "then the agent/infra model."),
        ConfigParam("metrics_filename", str, default="metrics.json",
                    description="Artefact filename written next to run_info.json."),
    ]

    async def execute(self, ctx: ExecutionContext) -> StepOutput:
        from mas.library.eval.mce.runner import (
            ALL_SESSION_METRICS,
            build_metrics_document,
            compute_session_metrics,
        )

        config = self.config
        run_dir = run_dir_from_ctx(ctx, config)
        events_raw = config.get("events_path") or config.get("trace_path")
        events_path = (
            Path(str(events_raw)).expanduser().resolve()
            if events_raw
            else resolve_run_events(ctx, config)
        )
        if events_path is None or not events_path.exists():
            raise RuntimeError(
                f"EvalMceStep '{self.name}' requires the run-level events artifact "
                "(traces/events.jsonl). Place this step in run.post with in: trace."
            )

        run_folder = Path(run_dir) if run_dir else events_path.parent.parent
        metrics_file = run_folder / str(config.get("metrics_filename", "metrics.json"))
        overwrite = bool(config.get("overwrite", False))
        if metrics_file.exists() and not overwrite:
            return StepOutput(
                data={"total": 1, "computed": 0, "skipped": 1, "errors": 0},
                files=[],
                metadata={"skipped": True},
            )

        test = str(config.get("test") or "")
        item_id = test[4:] if test.startswith("item") else test
        metric_names = config.get("metrics") or ALL_SESSION_METRICS
        judge_model, judge_source = _install_judge(config, ctx)

        loop = asyncio.get_event_loop()
        max_workers = int(config.get("max_workers", 2))
        try:
            async with _judge_semaphore(max_workers):
                session_scores = await loop.run_in_executor(
                    None,
                    functools.partial(
                        compute_session_metrics,
                        events_path,
                        metric_names,
                        response_agent_id=config.get("response_agent") or None,
                    ),
                )
            doc = build_metrics_document(
                item_id=item_id,
                scenario=str(config.get("scenario") or ""),
                session_scores=session_scores,
            )
            if bool(config.get("validate", True)):
                schema = _load_metrics_schema()
                if schema is not None:
                    _validate_document(doc, schema, events_path)
        except Exception as exc:
            logger.error("EvalMceStep '%s': scoring failed for %s: %s", self.name, events_path, exc)
            doc = build_metrics_document(
                item_id=item_id, scenario=str(config.get("scenario") or ""), session_scores={}
            )
            doc.setdefault("run_quality", {})["status"] = "error"
            doc["run_quality"].setdefault("errors", []).append(str(exc))
            metrics_file.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return StepOutput(
                data={"total": 1, "computed": 0, "skipped": 0, "errors": 1},
                files=[metrics_file],
                metadata={
                    "output": str(metrics_file),
                    "error": str(exc),
                    "judge_model": judge_model,
                    "judge_model_source": judge_source,
                },
            )
        run_ref = run_folder / ".run_ref"
        if run_ref.exists():
            try:
                run_hash = run_ref.read_text(encoding="utf-8").strip()
                doc["run_hash"] = run_hash
                doc["cache_key"] = run_hash
            except Exception:
                logger.debug("suppressed", exc_info=True)
        metrics_file.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return StepOutput(
            data={"total": 1, "computed": 1, "skipped": 0, "errors": 0},
            files=[metrics_file],
            metadata={
                "output": str(metrics_file),
                "judge_model": judge_model,
                "judge_model_source": judge_source,
            },
        )

    def outputs_exist(self, output_dir: Path) -> bool:
        return False


def _load_metrics_schema() -> Optional[Dict[str, Any]]:
    from mas.lab.schemas.paths import lab_artefact_schema_dir

    schema_path = lab_artefact_schema_dir() / "metrics.schema.json"
    if not schema_path.exists():
        return None
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load metrics schema: %s", exc)
        return None


def _validate_document(
    doc: Dict[str, Any], schema: Dict[str, Any], trace_path: Path
) -> None:
    try:
        import jsonschema

        jsonschema.validate(doc, schema)
    except ImportError:
        logger.debug("jsonschema not installed — skipping metrics validation")
    except Exception as exc:
        logger.warning("metrics.json validation failed for %s: %s", trace_path, exc)
