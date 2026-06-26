#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas-lab eval — CLI command for scoring MAS output quality with MCE metrics.

Usage::

    # Score a single trace
    mas-lab eval path/to/events.jsonl --metric GoalSuccessRate --metric Groundedness

    # Batch scoring (recursive)
    mas-lab eval path/to/experiment/ --metric GoalSuccessRate --recursive

    # List available metrics
    mas-lab eval --list-metrics
"""
from __future__ import annotations

import asyncio
import json as _json
from pathlib import Path
from typing import Optional

import click

from mas.library.eval.mce import (
    compute_session_metrics,
    build_session_from_trace,
    METRIC_REGISTRY,
)


@click.command("eval")
@click.argument("source", type=str, required=False)
@click.option(
    "--metric", "metrics", multiple=True,
    help=(
        "Metric(s) to compute (repeatable). "
        "Use --list-metrics to show available metrics."
    ),
)
@click.option(
    "--model",
    default="azure/gpt-4o",
    show_default=True,
    help="LLM model name for judge metrics",
)
@click.option(
    "--api-base",
    default="https://api.openai.com/v1",
    show_default=True,
    help="API base URL for LLM proxy",
)
@click.option(
    "--api-key-env",
    default="OPENAI_API_KEY",
    show_default=True,
    help="Environment variable holding the API key",
)
@click.option(
    "--json", "output_json", is_flag=True, default=False,
    help="Output results as JSON",
)
@click.option(
    "--list-metrics", is_flag=True, default=False,
    help="List available metrics and exit",
)
@click.option(
    "--recursive", is_flag=True, default=False,
    help="Recursively score all traces in SOURCE directory",
)
def eval_cmd(
    source: Optional[str],
    metrics: tuple[str, ...],
    model: str,
    api_base: str,
    api_key_env: str,
    output_json: bool,
    list_metrics: bool,
    recursive: bool,
) -> None:
    """Score MAS output quality using MCE v1 LLM-as-judge metrics.

    SOURCE can be:
    - Path to events.jsonl trace file
    - Directory containing traces (with --recursive)
    - Lab shorthand (e.g., baseline/item1/r1)

    \b
    Examples:
      mas-lab eval path/to/events.jsonl --metric GoalSuccessRate
      mas-lab eval experiments/ --metric GoalSuccessRate --recursive
      mas-lab eval --list-metrics
    """
    if list_metrics:
        _print_metrics()
        return

    if not source:
        click.echo("❌  SOURCE argument required (or use --list-metrics)")
        raise SystemExit(1)

    if not metrics:
        click.echo("❌  At least one --metric required (or use --list-metrics)")
        raise SystemExit(1)

    # Resolve source path
    source_path = Path(source).expanduser()
    if not source_path.exists():
        click.echo(f"❌  Source not found: {source}")
        raise SystemExit(1)

    # Build LLM config
    import os
    llm_config = {
        "LLM_MODEL_NAME": model,
        "LLM_BASE_MODEL_URL": api_base,
        "LLM_API_KEY": os.environ.get(api_key_env, ""),
    }

    if not llm_config["LLM_API_KEY"]:
        click.echo(f"❌  Environment variable {api_key_env} not set")
        raise SystemExit(1)

    # Run evaluation
    if recursive and source_path.is_dir():
        _eval_recursive(source_path, list(metrics), llm_config, output_json)
    elif source_path.is_file():
        _eval_single(source_path, list(metrics), llm_config, output_json)
    else:
        click.echo(f"❌  SOURCE must be a file or directory (with --recursive)")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eval_single(
    trace_path: Path,
    metrics: list[str],
    llm_config: dict,
    output_json: bool,
) -> None:
    """Evaluate a single trace file."""
    try:
        session = build_session_from_trace(trace_path)
    except Exception as exc:
        click.echo(f"❌  Failed to load trace {trace_path}: {exc}")
        raise SystemExit(1)

    # Run async computation
    results = asyncio.run(
        compute_session_metrics(session, metrics, llm_config)
    )

    if not results:
        click.echo("❌  No results")
        raise SystemExit(1)

    # Output
    if output_json:
        import dataclasses
        from datetime import datetime

        def _default(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            raise TypeError(f"Not serializable: {type(obj)}")

        click.echo(_json.dumps([dataclasses.asdict(r) for r in results], indent=2, default=_default))
    else:
        _print_table(results, trace_path.stem)


def _eval_recursive(
    root: Path,
    metrics: list[str],
    llm_config: dict,
    output_json: bool,
) -> None:
    """Recursively evaluate all traces under root directory."""
    trace_files = list(root.rglob("events.jsonl"))
    
    if not trace_files:
        click.echo(f"❌  No trace files found under {root}")
        raise SystemExit(1)

    click.echo(f"📊 Found {len(trace_files)} trace files")

    all_results = []
    for trace_path in trace_files:
        try:
            session = build_session_from_trace(trace_path)
            results = asyncio.run(
                compute_session_metrics(session, metrics, llm_config)
            )
            all_results.append((str(trace_path.relative_to(root)), results))
        except Exception as exc:
            click.echo(f"⚠️  Skipped {trace_path.name}: {exc}", err=True)
            continue

    if not all_results:
        click.echo("❌  No successful evaluations")
        raise SystemExit(1)

    # Output
    if output_json:
        import dataclasses
        from datetime import datetime

        def _default(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            raise TypeError(f"Not serializable: {type(obj)}")

        output = {
            path: [dataclasses.asdict(r) for r in results]
            for path, results in all_results
        }
        click.echo(_json.dumps(output, indent=2, default=_default))
    else:
        for path, results in all_results:
            click.echo(f"\n{'=' * 70}")
            click.echo(f"📁 {path}")
            click.echo('=' * 70)
            _print_table(results, path)


def _print_table(results, source_label: str) -> None:
    """Print results as a human-readable table."""
    click.echo(f"\n✅ Results for {source_label}:")
    click.echo()
    
    # Header
    header = f"{'Metric':<30} {'Value':>8} {'Success':>8}"
    click.echo(header)
    click.echo('-' * len(header))
    
    # Rows
    for result in results:
        metric_name = result.metric_name
        value = result.value if result.value is not None else "N/A"
        success = "✓" if result.success else "✗"
        
        if isinstance(value, float):
            value_str = f"{value:.3f}"
        else:
            value_str = str(value)
        
        click.echo(f"{metric_name:<30} {value_str:>8} {success:>8}")
    
    click.echo()
    
    # Reasoning (if available and not too long)
    for result in results:
        if result.reasoning and len(result.reasoning) < 200:
            click.echo(f"  {result.metric_name}: {result.reasoning[:150]}...")


def _print_metrics() -> None:
    """Print available metrics."""
    click.echo("\n📊 Available MCE v1 Metrics:\n")
    
    # Group by category
    quality_metrics = []
    core_metrics = []
    
    for name, spec in sorted(METRIC_REGISTRY.items()):
        if "mce_metrics_plugin" in spec:
            quality_metrics.append(name)
        else:
            core_metrics.append(name)
    
    click.echo("Quality Metrics (LLM-as-judge):")
    for name in quality_metrics:
        click.echo(f"  • {name}")
    
    click.echo("\nCore Metrics (rule-based):")
    for name in core_metrics:
        click.echo(f"  • {name}")
    
    click.echo()


# ---------------------------------------------------------------------------
# CLI Component for mas-lab extension system
# ---------------------------------------------------------------------------

class EvalCliComponent:
    """CLI component that registers the 'mas-lab eval' command.
    
    This component is discovered and loaded via the ``mas.lab.cli.components``
    entry point when ``mas-library-eval`` is installed.
    
    Usage::
        
        # Installed automatically when library-eval is installed
        pip install -e library-eval
        
        # Then available as:
        mas-lab eval path/to/events.jsonl --metric GoalSuccessRate
    """
    
    def register(self, app: click.Group) -> str:
        """Register the eval command on the main mas-lab CLI app.
        
        Args:
            app: The main Click group (mas-lab CLI)
            
        Returns:
            Command name that was registered ("eval")
        """
        app.add_command(eval_cmd, name="eval")
        return "eval"
