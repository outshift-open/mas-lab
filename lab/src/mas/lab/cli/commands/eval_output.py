#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Click wrapper for ``mas-lab eval-output`` — MCE-backed output quality scoring.

LLM calls go directly through the openai SDK (no litellm routing).
Configure via OPENAI_API_KEY + OPENAI_BASE_URL (or OPENAI_API_BASE) in .env.

Shared MCE computation logic lives in :mod:`mas.library.eval.mce.runner`.
"""
from __future__ import annotations

import json as _json
from pathlib import Path

import click

from mas.library.eval.mce.runner import (
    ALL_SESSION_METRICS,
    METRIC_MAP,
    compute_session_metrics,
    install_openai_llm_service,
)

_DEFAULT_METRICS = ["goal_success_rate"]


@click.command("eval-output")
@click.argument("trace", type=str, metavar="SOURCE")
@click.option(
    "--fixture", type=Path, default=None,
    help="Path to incident fixture YAML — provides ground truth.",
)
@click.option(
    "--metric", "metrics", multiple=True,
    help=(
        "MCE metric(s) to compute (repeatable). "
        f"Defaults to {_DEFAULT_METRICS} when omitted. "
        "Use --list-metrics to show available metrics per engine."
    ),
)
@click.option(
    "--response-agent", default=None, show_default="auto-detect from trace",
    help="agent_id whose last execution_end is the final response. Auto-detected when omitted.",
)
@click.option(
    "--model",
    default=None,
    show_default="infra manifest default (vertex_ai/gemini-3-pro-preview)",
    help="Override model name (infra manifest default is used when omitted).",
)
@click.option(
    "--json", "output_json", is_flag=True, default=False,
    help="Output results as JSON instead of a human-readable table.",
)
@click.option("--overlay", default=None, help="Label for display (e.g. inject-C7-backend).")
@click.option(
    "--engine",
    type=click.Choice(["mce-v1"]),
    default="mce-v1",
    show_default=True,
    help="Metric computation engine: mce-v1.",
)
@click.option(
    "--api-key-env", default=None,
    help="Name of the environment variable holding the API key (default: OPENAI_API_KEY).",
)
def eval_output_cmd(
    trace: str,
    fixture: Optional[Path],
    metrics: tuple[str, ...],
    response_agent: str,
    model: Optional[str],
    output_json: bool,
    overlay: Optional[str],
    engine: str,
    api_key_env: Optional[str],
) -> None:
    """Score MAS output quality using MCE LLM-as-judge metrics.

    SOURCE can be a file path (events.jsonl), a lab shorthand
    (e.g. tutorials/t3-analysis/baseline/item1/r1), or a run_id.

    \b
    Examples:
      mas-lab eval-output path/to/events.jsonl --metric goal_success_rate --json
      mas-lab eval-output tutorials/t3-analysis/baseline/item1/r1 --metric groundedness
    """
    # ── Resolve source path ──────────────────────────────────────────────
    from mas.lab.cli.commands.plot import resolve_source
    resolved = resolve_source(trace)
    trace_path = Path(resolved).expanduser()

    if not trace_path.exists():
        click.echo(f"❌  Trace file not found: {trace}")
        raise SystemExit(1)

    # ── Inject openai-SDK LLM service (bypasses litellm entirely) ───────────
    # Source: infra manifest (config.yaml → InfraManifest), --model overrides
    install_openai_llm_service(model, api_key_env=api_key_env)

    if fixture:
        if not fixture.exists():
            click.echo(f"❌  Fixture not found: {fixture}")
            raise SystemExit(1)
        # ground_truth is reserved for future use; current MCE LLM-judge
        # metrics score response quality without a reference answer.
        click.echo("ℹ️  --fixture provided but not consumed by current MCE metrics.", err=True)

    # ── Validate metric names ─────────────────────────────────────────────────
    metric_names = list(metrics) if metrics else _DEFAULT_METRICS
    unknown = [n for n in metric_names if n not in METRIC_MAP]
    for name in unknown:
        click.echo(
            f"⚠️  Unknown metric {name!r} — skipping.  Known: {', '.join(sorted(METRIC_MAP))}",
            err=True,
        )
    metric_names = [n for n in metric_names if n in METRIC_MAP]
    if not metric_names:
        click.echo("❌  No valid metrics to compute.")
        raise SystemExit(1)

    # ── Compute ───────────────────────────────────────────────────────────────
    results_dict = compute_session_metrics(
        trace_path,
        metric_names,
        response_agent_id=response_agent,
    )

    if not results_dict:
        click.echo("❌  No results — check trace content.")
        raise SystemExit(1)

    # ── Output ───────────────────────────────────────────────────────────────
    label = overlay or trace_path.stem
    if output_json:
        # Filter internal meta-keys (prefixed with __) from JSON output
        click.echo(_json.dumps({k: v for k, v in results_dict.items() if not k.startswith("__")}, indent=2))
    else:
        _print_v2_table(results_dict, label)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_v2_table(results_dict: dict, label: str) -> None:
    """Print MCE results in a human-readable table."""
    click.echo(f"\n{'─' * 72}")
    click.echo(f"  eval-output — {label}")
    click.echo(f"{'─' * 72}")
    click.echo(f"  {'Metric':<30}  {'Score':>6}  Reasoning")
    click.echo(f"  {'─'*30}  {'─'*6}  {'─'*30}")
    for name, result in results_dict.items():
        if name.startswith("__"):
            continue
        value = result.get("value")
        error = result.get("error")
        reasoning = (result.get("reasoning") or "").replace("\n", " ")[:60]
        score_str = f"{value:.3f}" if value is not None and not error else "ERR"
        click.echo(f"  {name:<30}  {score_str:>6}  {reasoning}")
    click.echo(f"{'─' * 72}\n")
