#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Worker implementations."""
from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from mas.lab.controller.io_capture import capture_worker_io
from mas.lab.controller.registry import WorkerRegistry
from mas.lab.controller.worker_model import WorkerKind, WorkerRecord, WorkerStatus

logger = logging.getLogger(__name__)


class WorkerRunner:
    """Runs worker callables in background threads."""

    def __init__(self, registry: WorkerRegistry) -> None:
        self.registry = registry
        self._cancel_flags: dict[str, threading.Event] = {}

    def submit(self, record: WorkerRecord, fn: Callable[[], Any]) -> None:
        cancel = threading.Event()
        self._cancel_flags[record.id] = cancel

        def _run() -> None:
            record.status = WorkerStatus.RUNNING
            record.started_at = time.time()
            record.pid = threading.get_ident()
            try:
                if cancel.is_set():
                    record.status = WorkerStatus.CANCELLED
                    return
                result = fn()
                if cancel.is_set():
                    record.status = WorkerStatus.CANCELLED
                elif result is False:
                    record.status = WorkerStatus.FAILED
                    record.exit_code = 1
                    record.error = "worker returned failure"
                else:
                    record.status = WorkerStatus.COMPLETED
                    record.exit_code = 0
                    record.result = result
            except Exception as exc:
                logger.exception("Worker %s failed", record.id)
                record.status = WorkerStatus.FAILED
                record.exit_code = 1
                record.error = str(exc)
                record.append_stderr(str(exc))
            finally:
                record.finished_at = time.time()
                self._cancel_flags.pop(record.id, None)

        threading.Thread(target=_run, daemon=True, name=f"worker-{record.id}").start()

    def cancel(self, worker_id: str) -> bool:
        event = self._cancel_flags.get(worker_id)
        if event is not None:
            event.set()
        return self.registry.cancel(worker_id)


def run_benchmark_worker(registry: WorkerRegistry, runner: "WorkerRunner", spec: dict) -> WorkerRecord:
    experiment_yaml = Path(spec["experiment_yaml"])
    cmd_parts = ["mas-lab", "benchmark", "run", str(experiment_yaml)]
    for flag in ("force", "dry_run", "single_run", "force_lock"):
        if spec.get(flag):
            cmd_parts.append(f"--{flag.replace('_', '-')}")
    record = registry.create(
        WorkerKind.BENCHMARK,
        spec=spec,
        command=" ".join(cmd_parts),
        endpoint=f"/api/benchmark/run",
    )

    def _execute() -> bool:
        from mas.lab.benchmark.engine import run_benchmark

        with capture_worker_io(record):
            ok = asyncio.run(
                run_benchmark(
                    experiment_yaml=experiment_yaml,
                    progress=spec.get("progress", True),
                    resume=spec.get("resume", False),
                    force=spec.get("force", False),
                    benchmark_id=spec.get("benchmark_id"),
                    dry_run=spec.get("dry_run", False),
                    max_runs=spec.get("max_runs"),
                    limit_scenarios=spec.get("limit_scenarios"),
                    sample_scenarios=spec.get("sample_scenarios"),
                    single_run=spec.get("single_run", False),
                    output_dir=Path(spec["output_dir"]) if spec.get("output_dir") else None,
                    trace_cache_dir=Path(spec["trace_cache_dir"]) if spec.get("trace_cache_dir") else None,
                    data_cache_dir=Path(spec["data_cache_dir"]) if spec.get("data_cache_dir") else None,
                    force_lock=spec.get("force_lock", False),
                    flavour_name=spec.get("flavour_name"),
                    infra_name=spec.get("infra_name"),
                    strategy=spec.get("strategy"),
                    step_overrides=spec.get("step_overrides") or [],
                    clean_stale=spec.get("clean_stale"),
                )
            )
        if not ok:
            raise RuntimeError("benchmark run failed")
        return ok

    runner.submit(record, _execute)
    return record


def run_application_worker(registry: WorkerRegistry, runner: "WorkerRunner", spec: dict) -> WorkerRecord:
    record = registry.create(
        WorkerKind.APPLICATION,
        spec=spec,
        command=spec.get("command", "application run"),
        endpoint=spec.get("endpoint", "/api/run"),
    )

    def _execute() -> dict:
        from mas.lab.runners.constants import DEFAULT_LAB_RUNNER_ID, normalize_runner_id
        from mas.lab.runners.factory import RunnerFactory

        runner_id = normalize_runner_id(spec.get("runner_id", DEFAULT_LAB_RUNNER_ID))
        app_runner = RunnerFactory.get(runner_id)
        output_dir = Path(spec.get("output_dir") or tempfile.mkdtemp(prefix="mas-lab-run-"))
        output_dir.mkdir(parents=True, exist_ok=True)
        result = app_runner.run(
            spec["prompt"],
            config=spec.get("config") or {},
            spec_path=Path(spec["spec_path"]),
            flavour=spec.get("flavour"),
            output_dir=output_dir,
            turns=spec.get("turns"),
            session_id=spec.get("session_id"),
            memory_seeds=spec.get("memory_seeds"),
            run_seed=spec.get("run_seed", 0),
            emulation_plugins=spec.get("emulation_plugins"),
        )
        return {
            "content": result.content,
            "status": result.status,
            "error": result.error,
            "output_dir": str(output_dir),
            "metadata": result.metadata,
        }

    runner.submit(record, _execute)
    return record


def run_pipeline_worker(registry: WorkerRegistry, runner: "WorkerRunner", spec: dict) -> WorkerRecord:
    record = registry.create(
        WorkerKind.PIPELINE,
        spec=spec,
        command=spec.get("command", "pipeline run"),
        endpoint="/api/pipeline/run",
    )

    def _execute() -> Any:
        import asyncio
        from pathlib import Path

        from mas.lab.benchmark.pipeline import Pipeline, PipelineExecutor
        from mas.lab.benchmark.pipeline.cli import _load_lab_custom_steps

        pipeline_yaml = Path(spec["pipeline_yaml"])
        _load_lab_custom_steps(pipeline_yaml.resolve())
        pipeline = Pipeline.from_yaml(pipeline_yaml)
        executor = PipelineExecutor(
            pipeline,
            output_dir=Path(spec["output_dir"]) if spec.get("output_dir") else None,
        )
        result = asyncio.run(
            executor.run(
                steps=spec.get("only"),
                force_rerun=spec.get("force"),
                dry_run=spec.get("dry_run", False),
                parallel=spec.get("parallel", False),
                template_vars=spec.get("variables") or {},
            )
        )
        if not result.success:
            raise RuntimeError(f"pipeline failed — {result.summary()}")
        return {"success": True, "summary": result.summary()}

    runner.submit(record, _execute)
    return record
