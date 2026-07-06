#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Execute MAS benchmark runs according to the execution plan."""

import asyncio
import logging
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mas.lab.benchmark.cache.trace_store import (
    compute_run_hash,
    extract_flavour_info,
    get_trace_cache_dir,
    link_trace_to_cache_entry,
    write_cache_inputs,
    write_run_info,
    write_run_result,
)
from mas.lab.benchmark.execution import build_execution_plan
from mas.lab.benchmark.schedule.metadata import execution_as_dict
from mas.lab.benchmark.schedule.run_batch.load import LoadedExperiment
from mas.lab.benchmark.schedule.run_batch.prepare import PreparedBatch
from mas.lab.runners.context import RunContext
from mas.lab.runners.invoke import invoke_runner

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Aggregated results from the run loop."""

    results_rows: list
    total_ok: int
    total_fail: int
    exit_stack: Any


async def execute_batch(
    loaded: LoadedExperiment,
    prepared: PreparedBatch,
    *,
    progress: bool = True,
    force: bool = False,
    strategy: Optional[str] = None,
) -> ExecutionResult:
    """Run all planned (scenario × item × run) executions."""
    import contextlib
    from mas.lab.benchmark.service_manager import ServiceManager as _ServiceManager
    from mas.lab.emulation_resolver import resolve_emulation_plugins

    exp = loaded.exp
    experiment_yaml = loaded.experiment_yaml
    _flavour = loaded.flavour
    flavour_name = loaded.flavour_name
    trace_cache_dir = loaded.trace_cache_dir
    output_dir = prepared.output_dir

    _mas_manifest_path = exp.mas.manifest if (exp.mas and exp.mas.manifest) else experiment_yaml

    _svc_mgr = _ServiceManager.for_benchmark(
        flavour=_flavour,
        experiment_dir=experiment_yaml.parent,
        output_dir=output_dir,
    )
    _exit_stack = contextlib.ExitStack()
    _exit_stack.enter_context(_svc_mgr)

    results_rows: list = []
    total_ok = 0
    total_fail = 0

    _effective_strategy = (
        strategy
        or (getattr(exp.execution, "strategy", None) if exp.execution else None)
        or "coverage"
    )
    _execution_plan = build_execution_plan(
        prepared.loaded_ids,
        prepared.dataset_items,
        loaded.n_runs,
        strategy=_effective_strategy,
        execution=execution_as_dict(exp),
    )

    _parallel = max(1, (getattr(exp.execution, "parallel_scenarios", 1) if exp.execution else 1) or 1)
    _pause    = max(0.0, (getattr(exp.execution, "pause_between_runs", 0.0) if exp.execution else 0.0) or 0.0)
    _sem      = asyncio.Semaphore(_parallel)
    _io_lock  = asyncio.Lock()

    _emulation = getattr(exp.execution, "emulation", None)
    _cache_policy = getattr(getattr(_emulation, "runtime", None), "cache", "content-addressed") if _emulation else "content-addressed"

    if progress:
        print()
        print(f"Running MAS benchmark '{exp.name}'")
        print(f"  strategy   : {_effective_strategy}")
        print(f"  {len(prepared.loaded_ids)} scenarios × {len(prepared.dataset_items)} items × {loaded.n_runs} run(s) = {len(_execution_plan)} executions")
        print(f"  parallel   : {_parallel}   pause: {_pause}s")
        if _emulation:
            _inf = _emulation.infra
            _state_parts = [f"llm={_inf.llm}", f"tools={_inf.tools}", f"memory={_inf.memory}"]
            if _inf.embeddings != "live":
                _state_parts.append(f"embeddings={_inf.embeddings}")
            if _inf.state != "live":
                _state_parts.append(f"state={_inf.state}")
            _state_parts.append(f"cache={_cache_policy}")
            print(f"  emulation  : {'  '.join(_state_parts)}")
        print()

    _faults_config = getattr(exp.execution, "faults", None) if exp.execution else None
    _faults_dict = _faults_config if isinstance(_faults_config, dict) else None
    _emulation_plugins = resolve_emulation_plugins(
        _emulation,
        faults_config=_faults_dict,
    )

    async def _run_one(scenario_id: str, item: dict, run_idx: int) -> None:
        nonlocal total_ok, total_fail
        config, spec_path = prepared.scenario_configs[scenario_id]
        item_id = item.get("id", 0)

        from mas.lab.inputs import load_run_input, run_input_to_dict

        _sc_spec_for_input = exp.get_scenario(scenario_id)
        _scenario_raw = None
        if _sc_spec_for_input is not None:
            _scenario_raw = {
                "inputs": getattr(_sc_spec_for_input, "inputs", {}) or {},
                "expectations": getattr(_sc_spec_for_input, "expectations", {}) or {},
            }
        _run_input = load_run_input(
            item,
            scenario=_scenario_raw,
            base_path=exp.base_dir if hasattr(exp, "base_dir") else output_dir.parent,
        )
        prompt = _run_input.primary_prompt
        _run_input_dict = run_input_to_dict(_run_input)
        if not prompt:
            return
        t0 = _time.monotonic()
        error: Optional[str] = None
        output = ""
        status = "ok"

        run_id = f"{scenario_id}__item{item_id}__r{run_idx + 1}"

        _sc_flavour = _flavour
        _sc_spec_flavour = exp.get_scenario(scenario_id)
        if _sc_spec_flavour and getattr(_sc_spec_flavour, "flavour", None):
            _sc_flavour = prepared.scenario_flavours.get(scenario_id, _flavour)

        _flavour_info = extract_flavour_info(_sc_flavour)
        _run_hash = compute_run_hash(
            config,
            _run_input_dict,
            item_id,
            run_idx,
            _flavour_info,
            base_path=spec_path,
        )
        _trace_cache = get_trace_cache_dir(explicit=trace_cache_dir)
        _global_run_dir = _trace_cache / _run_hash
        _cached_events = _global_run_dir / "traces" / "events.jsonl"

        _sc_spec = exp.get_scenario(scenario_id)
        _sc_dir_name = _sc_spec.output_dir_name if _sc_spec else scenario_id
        run_output_dir = output_dir / _sc_dir_name / f"item{item_id}" / f"r{run_idx + 1}"
        run_output_dir.mkdir(parents=True, exist_ok=True)
        _events_path = run_output_dir / "traces" / "events.jsonl"

        _use_cache = _cache_policy != "disabled"
        _global_hit = (
            _use_cache
            and not force
            and _cached_events.exists()
            and _cached_events.stat().st_size > 0
        )
        _local_hit = (
            _use_cache
            and not force
            and not _global_hit
            and _events_path.exists()
            and not _events_path.is_symlink()
            and _events_path.stat().st_size > 0
        )
        if _cache_policy == "forced" and not _global_hit and not _local_hit:
            error = f"emulation.runtime.cache=forced but no cache entry for hash {_run_hash[:12]}"
            status = "error"
            async with _io_lock:
                total_fail += 1
                results_rows.append({
                    "run_id": run_id, "scenario": scenario_id,
                    "item_id": item_id, "run": run_idx + 1,
                    "group": item.get("group", ""),
                    "target_agents": ",".join(item.get("target_agents", [])),
                    "prompt": prompt,
                    "status": status, "output": "", "output_length": 0,
                    "trace_path": "", "elapsed_ms": 0.0, "error": error,
                })
            if progress:
                print(f"  ❌ [{scenario_id}] item={item_id} run={run_idx+1} (cache=forced, miss)")
            return
        if _global_hit or _local_hit:
            _src = "cached:" + _run_hash[:8] if _global_hit else "local"
            if _global_hit:
                link_trace_to_cache_entry(run_output_dir, _global_run_dir, _run_hash)
            write_run_info(
                _global_run_dir, run_output_dir, _run_hash, exp.name, scenario_id,
                item_id, run_idx,
                app=prepared.mas_app,
                app_version=prepared.mas_app_version,
                mas_ref=prepared.mas_ref,
                overlay_ref=prepared.scenario_overlay_refs.get(scenario_id, ""),
            )
            if progress:
                print(f"  ⏩  [{scenario_id}] item={item_id} run={run_idx+1} ({_src}, skipping)")
            resolved_events = _cached_events if _global_hit else _events_path
            async with _io_lock:
                results_rows.append({
                    "run_id": run_id,
                    "scenario": scenario_id,
                    "item_id": item_id,
                    "run": run_idx + 1,
                    "group": item.get("group", ""),
                    "target_agents": ",".join(item.get("target_agents", [])),
                    "prompt": prompt,
                    "status": "ok",
                    "output": "(cached)",
                    "output_length": 0,
                    "trace_path": str(resolved_events),
                    "elapsed_ms": 0.0,
                    "error": "",
                })
                total_ok += 1
            return

        if _events_path.is_symlink():
            _events_path.unlink()
        elif _events_path.exists():
            _events_path.unlink()
        for _span_name in ("otel_sdk_spans.jsonl", "observe_sdk_spans.jsonl"):
            for _traces_root in (run_output_dir / "traces", _global_run_dir / "traces"):
                _span_path = _traces_root / _span_name
                if _span_path.is_file():
                    _span_path.unlink()
        # Remove the traces dir/symlink from run_output_dir so that
        # link_trace_to_cache_entry (called in the finally block) can create a
        # clean symlink run_output_dir/traces → cache/<hash>/traces.  Without
        # this, a pre-existing real directory would block symlink creation and
        # cause a .run_ref-only fallback.
        _run_traces_dir = run_output_dir / "traces"
        if _run_traces_dir.is_symlink():
            _run_traces_dir.unlink()
        elif _run_traces_dir.is_dir():
            # Safety: only rmtree a directory that is strictly under run_output_dir.
            # Guards against the (unlikely) case where run_output_dir itself is a
            # symlink whose resolved path puts traces/ outside the experiment tree.
            if _run_traces_dir.resolve().is_relative_to(run_output_dir.resolve()):
                import shutil as _shutil_exec
                _shutil_exec.rmtree(_run_traces_dir)
            else:
                logger.warning(
                    "Skipping rmtree: %s resolves outside run_output_dir %s",
                    _run_traces_dir, run_output_dir,
                )
        _cached_events_backup: Optional[Path] = None
        if force and _cached_events.exists():
            _cached_events_backup = _cached_events.with_suffix(".jsonl.bak")
            _cached_events.rename(_cached_events_backup)

        async with _sem:
            if _pause > 0:
                await asyncio.sleep(_pause)

            _global_run_dir.mkdir(parents=True, exist_ok=True)
            try:
                def _do_mas_run() -> dict:
                    from mas.lab.runners.infer import infer_runner_id

                    _runner_id = infer_runner_id(
                        execution_runner=(
                            exp.execution.runner
                            if exp.execution and getattr(exp.execution, "runner", None)
                            else None
                        ),
                        mas_manifest=(
                            Path(_mas_manifest_path)
                            if _mas_manifest_path is not None
                            else None
                        ),
                        agent_config=config,
                        flavour=_sc_flavour if isinstance(_sc_flavour, dict) else None,
                    )
                    _overlay_refs = list(prepared.scenario_overlay_stacks.get(scenario_id, []))
                    _infra_refs = list(prepared.infra_refs)
                    if isinstance(_sc_flavour, dict):
                        _flavour_infra = list(_sc_flavour.get("infra_refs") or [])
                        if _flavour_infra:
                            _infra_refs = _flavour_infra
                    ctx = RunContext(
                        prompt=prompt,
                        config=config,
                        spec_path=spec_path,
                        output_dir=_global_run_dir,
                        runner_id=_runner_id,
                        run_input=_run_input,
                        flavour=_sc_flavour,
                        run_seed=run_idx,
                        overlay_refs=_overlay_refs,
                        overlays_dir=prepared.overlays_dir,
                        overlay_base_dir=prepared.overlay_base_dir,
                        infra_refs=_infra_refs,
                        session_id=_run_input.session_id,
                        emulation_plugins=_emulation_plugins,
                    )
                    result = invoke_runner(ctx)
                    return {
                        "content": result.content,
                        "status": result.status,
                        "usage": result.metadata.get("usage", {}),
                        "agent_id": result.metadata.get("agent_id", ""),
                    }

                result_dict = await asyncio.to_thread(_do_mas_run)
                output = result_dict.get("content", str(result_dict))
                if result_dict.get("status") == "error":
                    error = output or "execution error"
                    status = "error"
                elif output and output.startswith("LLM request failed:"):
                    # classify_llm_http_error returns a string that becomes the
                    # agent response content — the runner doesn't raise, so
                    # status stays "ok". Treat it as an execution error so that
                    # the run is counted as failed rather than silently passing.
                    error = output
                    status = "error"
                write_cache_inputs(
                    _global_run_dir, _run_hash, _run_input_dict, item_id,
                    run_idx, _flavour_info,
                )
            except Exception as exc:
                error = str(exc)
                status = "error"
                async with _io_lock:
                    total_fail += 1
            else:
                async with _io_lock:
                    if status == "error":
                        total_fail += 1
                    else:
                        total_ok += 1
            finally:
                link_trace_to_cache_entry(run_output_dir, _global_run_dir, _run_hash)
                if _cached_events_backup is not None and _cached_events_backup.exists():
                    if _cached_events.exists() and _cached_events.stat().st_size > 0:
                        _cached_events_backup.unlink()
                    else:
                        _cached_events_backup.rename(_cached_events)
                if status == "ok" and _cached_events.is_file() and _cached_events.stat().st_size > 0:
                    from mas.ctl.benchmark.runner import (
                        bench_obs_config,
                        ensure_live_otel_span_files,
                    )

                    _obs_events, _obs_cfg = bench_obs_config(
                        _global_run_dir,
                        config,
                        spec_path,
                        flavour=_sc_flavour if isinstance(_sc_flavour, dict) else None,
                    )
                    ensure_live_otel_span_files(_obs_events, _obs_cfg)

        trace_path = str(_cached_events)
        elapsed_ms = (_time.monotonic() - t0) * 1000
        write_run_result(_global_run_dir, status, elapsed_ms, error or "")
        write_run_info(
            _global_run_dir, run_output_dir, _run_hash, exp.name, scenario_id,
            item_id, run_idx,
            app=prepared.mas_app,
            app_version=prepared.mas_app_version,
            mas_ref=prepared.mas_ref,
            overlay_ref=prepared.scenario_overlay_refs.get(scenario_id, ""),
        )
        async with _io_lock:
            results_rows.append({
                "run_id": run_id,
                "scenario": scenario_id,
                "item_id": item_id,
                "run": run_idx + 1,
                "group": item.get("group", ""),
                "target_agents": ",".join(item.get("target_agents", [])),
                "prompt": prompt,
                "status": status,
                "output": output[:500],
                "output_length": len(output),
                "trace_path": trace_path,
                "elapsed_ms": round(elapsed_ms, 1),
                "error": error or "",
            })

        if progress:
            tag = "✅" if status == "ok" else "❌"
            print(f"  {tag} [{scenario_id}] item={item_id} run={run_idx+1} ({elapsed_ms:.0f}ms)")

    async def _dispatch_all() -> None:
        tasks = []
        for sid, itm, ridx in _execution_plan:
            tasks.append(asyncio.create_task(_run_one(sid, itm, ridx)))
        await asyncio.gather(*tasks, return_exceptions=True)

    await _dispatch_all()

    return ExecutionResult(
        results_rows=results_rows,
        total_ok=total_ok,
        total_fail=total_fail,
        exit_stack=_exit_stack,
    )
