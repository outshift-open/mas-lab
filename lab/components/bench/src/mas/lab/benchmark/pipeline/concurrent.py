#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from mas.lab.benchmark.pipeline.core import PipelineStep
from mas.lab.benchmark.pipeline.models import StepOutput
from mas.lab.benchmark.pipeline.resources import ScopeContext

if TYPE_CHECKING:
    from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)

_CONCURRENT_RUNNER_TYPE = "__concurrent_runner__"


class ConcurrentRunnerStep(PipelineStep):
    """Engine-internal wrapper: runs N per-run child steps with bounded concurrency.

    Created by materialize_step_dicts when a PipelineStepSpec has scope=run and
    concurrency > 1. Never declared directly in user YAML.

    Config keys (set by materialize_step_dicts, not user-facing):
        steps (list[dict]): materialized per-run step dicts
        concurrency (int): asyncio.Semaphore limit

    Each child's output is written to ctx.step_outputs[child.name] so downstream
    steps referencing individual per-run names by name can find their outputs.
    """

    type: str = _CONCURRENT_RUNNER_TYPE

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        child_dicts: List[Dict[str, Any]] = self.config.get("steps", [])
        concurrency: int = int(self.config.get("concurrency", 1))

        if not child_dicts:
            return StepOutput(
                data={},
                metadata={"total": 0, "succeeded": 0, "failed": 0, "concurrency": concurrency},
            )

        base_dir = (
            ctx.pipeline.config_path.parent
            if ctx.pipeline.config_path
            else Path.cwd()
        )
        child_steps: List[PipelineStep] = [
            PipelineStep.from_dict(sd, base_dir=base_dir) for sd in child_dicts
        ]

        sem = asyncio.Semaphore(concurrency)
        results: Dict[str, StepOutput] = {}
        failed: List[str] = []

        async def _run_one(step: PipelineStep) -> None:
            # Shallow copy isolates scope_context rebinding without duplicating step_outputs.
            # Plain dict writes to ctx.step_outputs are safe in asyncio (no preemption on
            # dict operations between awaits).
            child_ctx = copy.copy(ctx)
            cfg = step.config or {}
            if cfg.get("scenario") or cfg.get("run"):
                child_ctx.scope_context = ScopeContext(
                    experiment=ctx.scope_context.experiment,
                    scenario=str(cfg.get("scenario", "")),
                    test=str(cfg.get("test", "")),
                    run=str(cfg.get("run", "")),
                )
            # Mirror _execute_step: inject events_path, trace_path, and run_dir
            # from the run directory, same as the sequential executor does.
            from mas.lab.benchmark.pipeline.run_artifacts import run_input_stream
            run_payload = run_input_stream(child_ctx, cfg)
            if run_payload:
                step.config.setdefault("run_dir", run_payload.get("run_dir", ""))
                for key in ("scenario", "test", "run", "events_path", "trace_path"):
                    if run_payload.get(key) and not step.config.get(key):
                        step.config[key] = run_payload[key]
            async with sem:
                try:
                    output = await step.execute(child_ctx)
                    ctx.step_outputs[step.name] = output
                    results[step.name] = output
                    logger.debug("concurrent runner: child '%s' succeeded", step.name)
                except Exception as exc:
                    logger.error(
                        "ConcurrentRunnerStep '%s': child '%s' failed: %s",
                        self.name, step.name, exc,
                        exc_info=True,
                    )
                    failed.append(step.name)

        await asyncio.gather(*[_run_one(s) for s in child_steps])

        if failed:
            raise RuntimeError(
                f"ConcurrentRunnerStep '{self.name}': "
                f"{len(failed)}/{len(child_steps)} child steps failed: {failed}"
            )

        return StepOutput(
            data={"results": {name: so.data for name, so in results.items()}},
            files=[f for so in results.values() for f in so.files],
            metadata={
                "total": len(child_steps),
                "succeeded": len(results),
                "failed": 0,
                "concurrency": concurrency,
            },
        )


__all__ = ["ConcurrentRunnerStep", "_CONCURRENT_RUNNER_TYPE"]
