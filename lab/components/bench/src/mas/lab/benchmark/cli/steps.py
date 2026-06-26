#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Benchmark step inspection and restart commands."""

import asyncio
import logging
from pathlib import Path

from mas.lab.benchmark.run_manager import BenchmarkRunManager

from mas.lab.benchmark.cli.common import _resolve_run_manager_dir

logger = logging.getLogger(__name__)

def step_list_command(args) -> int:
    """List all steps/scenarios in a benchmark run."""
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )
    
    # Get run
    result = run_manager.get_run(args.benchmark_id)
    if not result:
        logger.error(f"Benchmark run not found: {args.benchmark_id}")
        return 1
    
    metadata, run_dir = result
    
    # Load state
    state = run_manager.load_state(run_dir)
    if not state:
        logger.error("No state file found for this benchmark")
        return 1
    
    # Detect stale scenarios
    stale_count = state.detect_stale()
    if stale_count > 0:
        logger.info(f"Detected {stale_count} stale scenarios")
    
    # Print header
    print()
    print(f"Steps in benchmark: {metadata.short_id} ({metadata.name or 'unnamed'})")
    print("=" * 80)
    print()
    
    # Group by state
    state_groups = [
        ("🟢 COMPLETED", state.completed_scenarios),
        ("🔴 FAILED", state.failed_scenarios),
        ("🔵 RUNNING", state.running_scenarios),
        ("⚠️  STALE", state.stale_scenarios),
        ("⚪ TODO", state.todo_scenarios),
    ]
    
    for label, scenario_ids in state_groups:
        if scenario_ids:
            print(f"{label} ({len(scenario_ids)}):")
            for sid in sorted(scenario_ids):
                result = state.scenarios.get(sid)
                if result and result.started_at:
                    print(f"  {sid}")
                else:
                    print(f"  {sid}")
            print()
    
    # Summary
    print(f"Total: {len(state.scenarios)} scenarios")
    print(f"  Completed: {state.success_count}")
    print(f"  Failed: {state.failed_count}")
    print(f"  Running: {len(state.running_scenarios)}")
    print(f"  Stale: {len(state.stale_scenarios)}")
    print(f"  Pending: {len(state.todo_scenarios)}")
    print()
    
    return 0


def step_show_command(args) -> int:
    """Show details of a specific step/scenario."""
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )
    
    # Get run
    result = run_manager.get_run(args.benchmark_id)
    if not result:
        logger.error(f"Benchmark run not found: {args.benchmark_id}")
        return 1
    
    metadata, run_dir = result
    
    # Load state
    state = run_manager.load_state(run_dir)
    if not state:
        logger.error("No state file found for this benchmark")
        return 1
    
    step_id = args.step_id
    
    # Find scenario
    if step_id not in state.scenarios:
        logger.error(f"Step not found: {step_id}")
        return 1
    
    result = state.scenarios[step_id]
    
    # Print details
    print()
    print(f"Step: {step_id}")
    print("=" * 80)
    print()
    print(f"Status:      {result.state.value.upper()}")
    print(f"Success:     {result.success if result.success is not None else 'N/A'}")
    
    if result.started_at:
        print(f"Started:     {result.started_at}")
    
    if result.completed_at:
        print(f"Completed:   {result.completed_at}")
    
    if result.duration_seconds:
        print(f"Duration:    {result.duration_seconds:.2f}s")
    
    if result.process_pid:
        print(f"Process PID: {result.process_pid}")
    
    if result.score is not None:
        print(f"Score:       {result.score}")
    
    if result.tokens_total > 0:
        print(f"Tokens:      {result.tokens_total} (in: {result.tokens_input}, out: {result.tokens_output})")
    
    if result.error:
        print()
        print("Error:")
        print(f"  {result.error}")
    
    if result.result:
        print()
        print("Result Data:")
        for key, value in result.result.items():
            print(f"  {key}: {value}")
    
    # Try to find log file
    log_path = run_dir / "logs" / f"{step_id}.log"
    if log_path.exists():
        print()
        print(f"Log file: {log_path}")
        print()
        print("Last 20 lines:")
        print("-" * 80)
        try:
            with open(log_path) as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    print(f"  {line.rstrip()}")
        except Exception as e:
            print(f"  (could not read log: {e})")
    
    print()
    
    return 0


def step_restart_command(args) -> int:
    """Restart a single MAS benchmark run (clears trace, re-invokes batch loop)."""
    run_manager = BenchmarkRunManager(
        benchmarks_root=_resolve_run_manager_dir(getattr(args, "output_dir", None))
    )

    result = run_manager.get_run(args.benchmark_id)
    if not result:
        logger.error("Benchmark run not found: %s", args.benchmark_id)
        return 1

    metadata, run_dir = result
    experiment_yaml = Path(metadata.experiment_yaml_path)
    if not experiment_yaml.exists():
        logger.error("Experiment file not found: %s", experiment_yaml)
        return 1

    run_id = args.step_id
    print(f"\n🔄 Restarting run: {run_id}")
    print(f"   Benchmark: {metadata.short_id}")
    print(f"   Output: {run_dir}")
    print()

    try:
        from mas.lab.benchmark.engine import restart_mas_run

        ok = asyncio.run(
            restart_mas_run(
                run_dir=run_dir,
                experiment_yaml=experiment_yaml,
                run_id=run_id,
                progress=True,
            )
        )
        if ok:
            print(f"\n✅ Run restarted successfully: {run_id}")
            return 0
        print(f"\n❌ Run restart failed: {run_id}")
        return 1
    except ValueError as exc:
        logger.error("%s", exc)
        logger.info(
            "MAS run ids look like '{scenario}__item{id}__r{n}' "
            "(see results.csv run_id column)"
        )
        return 1
    except Exception as exc:
        logger.error("Failed to restart step: %s", exc)
        return 1

