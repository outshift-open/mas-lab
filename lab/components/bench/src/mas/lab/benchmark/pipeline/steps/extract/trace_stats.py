#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""ExtractTraceStatsStep — extract per-run governance and trajectory metrics
from events.jsonl trace files.

Scans ``<output_dir>/<scenario>/<item>/r<N>/traces/events.jsonl`` for every
scenario/item/run triple, computes a set of structural metrics from the raw
event stream, and writes a tidy CSV.

No LLM judge is invoked; all metrics are derived directly from trace events.

Output columns
--------------
scenario          str    Scenario folder name.
item              str    Item folder name (e.g. itemn1, itemf-budget).
item_group        str    Derived from item prefix: nominal / fault /
                         guardrail / recall / combination / other.
run               int    Run index (extracted from r<N> folder name).
duration_s        float  Wall-clock duration: max(timestamp) - min(timestamp).
n_governance_checks  int  Count of ``governance_checked`` events.
n_governance_fired   int  Count of ``governance_policy`` events where
                          ``outcome == "fired"``.
n_checks_passed      int  Sum of ``checks_passed`` across all
                          ``governance_event`` records — total number
                          of policy evaluations (scales with policy count).
n_tool_calls      int    Count of ``tool_call_start`` events.
n_llm_calls       int    Count of ``llm_call_start`` events.
n_context_tokens  int    Sum of ``token_estimate`` across
                         ``context_part_contributed`` events.
n_context_parts   int    Count of ``context_part_contributed`` events.

Configuration
-------------
output_dir   str   Root directory to scan. Defaults to ``ctx.output_dir``.
output       str   Output CSV path (default: ``trace_stats.csv`` inside
                   ``<output_dir>/results/``).
scenarios    list  Optional list of scenario IDs to include.
item_glob    str   Glob pattern for item directories (default: ``item*``).
run_glob     str   Glob pattern for run directories (default: ``r*``).

Example YAML::

    - name: extract-trace-stats
      type: extract_trace_stats
      config:
        output: "{output_dir}/results/trace_stats.csv"
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput

logger = logging.getLogger(__name__)

# Map item name prefix → group label
_GROUP_MAP = [
    ("itemn", "nominal"),
    ("itemf", "fault"),
    ("itemr", "recall"),
    ("itemc", "combination"),
    ("itemg", "guardrail"),
]


def _item_group(item: str) -> str:
    for prefix, group in _GROUP_MAP:
        if item.startswith(prefix):
            return group
    return "other"


def _run_index(run_dir: str) -> int:
    m = re.search(r"(\d+)", run_dir)
    return int(m.group(1)) if m else 0


def _extract_stats(events_path: Path) -> Dict[str, Any]:
    """Read one events.jsonl file and return a stats dict."""
    events: list = []
    try:
        with open(events_path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    except Exception as exc:
        logger.warning("Failed to read %s: %s", events_path, exc)
        return {}

    timestamps = [e["timestamp"] for e in events if isinstance(e.get("timestamp"), (int, float))]
    duration_s = (max(timestamps) - min(timestamps)) if len(timestamps) >= 2 else 0.0

    n_checks = sum(1 for e in events if e.get("kind") == "governance_checked")
    n_fired = sum(
        1 for e in events
        if e.get("kind") == "governance_policy" and e.get("outcome") == "fired"
    )
    n_checks_passed = sum(
        int(e.get("checks_passed") or 0)
        for e in events
        if e.get("kind") == "governance_event"
    )
    n_tool_calls = sum(1 for e in events if e.get("kind") == "tool_call_start")
    n_llm_calls = sum(1 for e in events if e.get("kind") == "llm_call_start")
    n_ctx_parts = sum(1 for e in events if e.get("kind") == "context_part_contributed")
    n_ctx_tokens = sum(
        e.get("token_estimate", 0) or 0
        for e in events
        if e.get("kind") == "context_part_contributed"
    )

    return {
        "duration_s": round(duration_s, 3),
        "n_governance_checks": n_checks,
        "n_governance_fired": n_fired,
        "n_checks_passed": n_checks_passed,
        "n_tool_calls": n_tool_calls,
        "n_llm_calls": n_llm_calls,
        "n_context_parts": n_ctx_parts,
        "n_context_tokens": n_ctx_tokens,
    }


from mas.lab.benchmark.cache.trace_store import resolve_run_events_path as _resolve_events_path
class ExtractTraceStatsStep(PipelineStep):
    """Extract per-run structural metrics from events.jsonl trace files."""

    type = "extract_trace_stats"

    async def execute(self, ctx: "Any") -> StepOutput:  # noqa: F821
        self._ctx = ctx
        config = self.config

        output_dir_raw = config.get("output_dir", "")
        output_dir = Path(output_dir_raw).expanduser() if output_dir_raw else ctx.output_dir

        output_raw = config.get("output", "")
        if output_raw:
            output_path = Path(output_raw).expanduser()
            if not output_path.is_absolute():
                output_path = output_dir / output_path
        else:
            output_path = output_dir / "results" / "trace_stats.csv"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        scenario_filter: Optional[List[str]] = config.get("scenarios")
        item_glob: str = config.get("item_glob", "item*")
        run_glob: str = config.get("run_glob", "r*")

        fieldnames = [
            "scenario", "item", "item_group", "run",
            "run_hash",
            "duration_s", "n_governance_checks", "n_governance_fired", "n_checks_passed",
            "n_tool_calls", "n_llm_calls", "n_context_parts", "n_context_tokens",
        ]

        rows: List[Dict[str, Any]] = []

        # Discover scenarios
        scenario_dirs = sorted(
            d for d in output_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name not in ("results", "data", "logs", "metadata.yaml")
            and (scenario_filter is None or d.name in scenario_filter)
        )

        for scenario_dir in scenario_dirs:
            scenario = scenario_dir.name
            item_dirs = sorted(scenario_dir.glob(item_glob))
            for item_dir in item_dirs:
                if not item_dir.is_dir():
                    continue
                item = item_dir.name
                run_dirs = sorted(item_dir.glob(run_glob))
                for run_dir in run_dirs:
                    if not run_dir.is_dir():
                        continue
                    events_path = _resolve_events_path(run_dir)
                    if events_path is None:
                        logger.debug("No events.jsonl for run_dir %s", run_dir)
                        continue
                    # Capture run_hash for unified cache linkage
                    _run_hash = ""
                    run_ref_f = run_dir / ".run_ref"
                    if run_ref_f.exists():
                        try:
                            _run_hash = run_ref_f.read_text(encoding="utf-8").strip()
                        except Exception:
                            logger.debug('suppressed', exc_info=True)
                    stats = _extract_stats(events_path)
                    if not stats:
                        continue
                    rows.append({
                        "scenario": scenario,
                        "item": item,
                        "item_group": _item_group(item),
                        "run": _run_index(run_dir.name),
                        "run_hash": _run_hash,
                        **stats,
                    })

        # Write CSV
        with open(output_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info("Wrote %d trace-stats rows to %s", len(rows), output_path)

        # Also expose as in-memory DataFrame (pandas) so downstream steps can
        # use @extract-trace-stats instead of a file path reference.
        try:
            import pandas as pd
            df = pd.DataFrame(rows, columns=fieldnames)
        except ImportError:
            df = None

        data: dict = {"df_path": str(output_path), "rows": len(rows)}
        if df is not None:
            data["df"] = df

        return StepOutput(
            data=data,
            files=[output_path],
            metadata={"scenarios": len(scenario_dirs), "rows": len(rows)},
        )
