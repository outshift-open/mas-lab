#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""GatherLevelStep — generic multi-level DataFrame gather-and-annotate operator.

This step is the backbone of multi-level experiment analysis.  It can be placed
at **any level** of the experiment hierarchy (run, test, scenario, experiment)
to propagate DataFrame results upward, annotating each row with the current
level's identifiers.

Architecture
------------
::

    run:
      pipeline:
        - name: extract-stats
          type: extract_trace_stats   # → data["df"] per run (no level columns yet)

        - name: gather-run
          type: gather_level
          depends_on: [extract-stats]
          config:
            annotate:                 # columns to add — values already interpolated
              scenario_id: "{scenario_id}"
              run_dir:     "{run_dir}"
            output: run_stats.csv    # optional: persist to run folder

    test:
      pipeline:
        - name: gather-test
          type: gather_level
          depends_on: [gather-run]   # runner fan-ins: gather-run-baseline, …
          config:
            output: test_stats.csv

    scenario:
      pipeline:
        - name: gather-scenario
          type: gather_level
          depends_on: [gather-test]
          config:
            output: scenario_stats.csv

    experiment:
      pipeline:
        - name: gather-experiment
          type: gather_level
          depends_on: [gather-scenario]
          config:
            output: results.csv      # final experiment-level tidy DataFrame

Two modes of operation
----------------------

**Stream mode** (primary — pipeline execution):
    When ``depends_on`` is set, the runner has fan-in'd each lower-level step
    instance into ``ctx.step_outputs``.  Each upstream step is expected to
    expose a DataFrame under ``data["df"]``.

    Optional ``annotate`` dict adds constant columns to each part **before**
    concatenation.  Values in ``annotate`` are strings that were already
    interpolated by the runner (e.g. ``"{scenario_id}"`` → ``"baseline"``).

**Lab API fallback** (offline / notebook):
    When ``depends_on`` is empty, uses the :class:`~mas.lab.labs.Lab` object
    model to iterate ``Experiment → Scenario → Run`` and loads the artifact
    named by ``artifact_name`` from each run directory.  Adds standard level
    columns (``scenario_id``, ``run_id``) automatically.

Resume via artifacts
--------------------
The step declares ``output_artifacts`` so the executor can restore its output
from disk without re-executing when the benchmark is resumed.

Downstream reference::

    - name: ci-analysis
      type: compute_ci
      config:
        data: "@gather-experiment"
        groupby: [scenario_id, metric]
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from mas.lab.benchmark.pipeline.executor import ExecutionContext

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.resources import Artifact, Scope

logger = logging.getLogger(__name__)


def _df_from_step_output(dep_name: str, out: "StepOutput") -> "Optional[pd.DataFrame]":
    """Extract a DataFrame from a StepOutput, trying several key conventions."""
    import pandas as pd

    data = out.data if isinstance(out.data, dict) else {}

    # 1. Canonical key: data["df"]
    val = data.get("df")
    if isinstance(val, pd.DataFrame):
        return val

    # 2. Defensive: the whole data is a DataFrame (should not happen with typed API)
    if isinstance(out.data, pd.DataFrame):
        return out.data

    # 3. Legacy: data["csv_path"] written by older steps
    csv_raw = data.get("csv_path")
    if csv_raw:
        p = Path(str(csv_raw))
        if p.exists():
            try:
                return pd.read_csv(p)
            except Exception as exc:
                logger.warning("gather_level: cannot read csv from dep '%s': %s", dep_name, exc)

    # 4. Legacy: data["parquet_path"]
    parquet_raw = data.get("parquet_path")
    if parquet_raw:
        p = Path(str(parquet_raw))
        if p.exists():
            try:
                return pd.read_parquet(p)
            except Exception as exc:
                logger.warning("gather_level: cannot read parquet from dep '%s': %s", dep_name, exc)

    return None


class GatherLevelStep(PipelineStep):
    """Generic gather-and-annotate step for multi-level experiment hierarchies.

    See module docstring for full documentation.

    Config keys
    -----------
    annotate : dict[str, str]
        Columns to add to every row of each gathered part.
        Values are already-interpolated strings (e.g. the runner substitutes
        ``"{scenario_id}"`` before the step executes).
    output : str
        Output file name relative to ``output_dir`` (default: ``"results.csv"``).
    output_dir : str
        Explicit root directory (default: pipeline's ``ctx.output_dir``).
    artifact_name : str
        Name of the per-run artifact to load in Lab API fallback mode
        (default: ``"results"``).
    format : str
        Output format: ``"csv"`` (default) or ``"parquet"``.
    """

    type = "gather_level"

    @property
    def output_artifacts(self) -> List[Tuple[str, Artifact]]:
        fmt = self.config.get("format", "csv")
        output_raw = self.config.get("output", f"results.{fmt}")
        output_path = Path(output_raw)
        artifact = Artifact(
            name=output_path.stem,
            format=fmt,
            scope=Scope.EXPERIMENT,
        )
        output_dir_raw = self.config.get("output_dir", "")
        if output_dir_raw and not output_path.is_absolute():
            artifact._resolved_path = Path(output_dir_raw) / output_path  # type: ignore[attr-defined]
        elif output_path.is_absolute():
            artifact._resolved_path = output_path  # type: ignore[attr-defined]
        return [("df_path", artifact)]

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        import pandas as pd

        config = self.config
        annotate: Dict[str, Any] = config.get("annotate") or {}
        fmt: str = config.get("format", "csv")
        artifact_name: str = config.get("artifact_name", "results")

        output_dir_raw = config.get("output_dir", "")
        output_dir = Path(output_dir_raw) if output_dir_raw else ctx.output_dir

        output_raw = config.get("output", f"results.{fmt}")
        output_path = Path(output_raw)
        if not output_path.is_absolute():
            output_path = output_dir / output_path

        frames: List["pd.DataFrame"] = []

        # ── Mode 1: stream — fan-in from upstream step outputs ───────────────
        # Each dep is an expanded instance (e.g. "gather-run-baseline").
        # The runner has already fan-in'd them so they are all in ctx.step_outputs.
        if self.depends_on:
            for dep_name in self.depends_on:
                dep_out = ctx.step_outputs.get(dep_name)
                if dep_out is None:
                    logger.warning(
                        "gather_level '%s': dep '%s' not in step_outputs (skipped)",
                        self.name, dep_name,
                    )
                    continue
                df_part = _df_from_step_output(dep_name, dep_out)
                if df_part is None or df_part.empty:
                    logger.debug(
                        "gather_level '%s': dep '%s' produced no DataFrame (skipped)",
                        self.name, dep_name,
                    )
                    continue
                df_part = df_part.copy()
                # 1. Annotate from the upstream step's metadata (scope identifiers
                #    written by the producing step, e.g. scenario_id, run_id).
                for col, val in dep_out.metadata.items():
                    if col not in df_part.columns:
                        df_part[col] = val
                # 2. Annotate with static columns from this step's config
                #    (values already interpolated by _inject_vars before execution).
                for col, val in annotate.items():
                    df_part[col] = val
                frames.append(df_part)

            if frames:
                logger.info(
                    "gather_level '%s': stream mode — gathered %d parts from %d deps",
                    self.name, len(frames), len(self.depends_on),
                )
            else:
                logger.warning(
                    "gather_level '%s': no DataFrames found in %d upstream deps; "
                    "falling back to Lab API traversal",
                    self.name, len(self.depends_on),
                )

        # ── Mode 2: Lab API fallback ─────────────────────────────────────────
        # When depends_on is empty (standalone / notebook / no upstream deps),
        # traverse the experiment hierarchy via the Lab object model.
        # Uses Run.artifacts(artifact_name).load() — no raw filesystem globbing.
        if not frames:
            frames = _collect_via_lab_api(output_dir, artifact_name)

        # ── Concatenate ──────────────────────────────────────────────────────
        if not frames:
            logger.warning("gather_level '%s': no data found in %s", self.name, output_dir)
            df = pd.DataFrame()
        else:
            df = pd.concat(frames, ignore_index=True)

        # ── Persist ──────────────────────────────────────────────────────────
        if not df.empty:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "parquet":
                df.to_parquet(output_path, index=False)
            else:
                df.to_csv(output_path, index=False)
            logger.info(
                "gather_level '%s': wrote %d rows × %d cols to %s",
                self.name, len(df), len(df.columns), output_path,
            )

        return StepOutput(
            data={"df": df, "df_path": str(output_path)},
            files=[output_path] if output_path.exists() else [],
            metadata={
                "rows": len(df),
                "cols": len(df.columns),
                "parts": len(frames),
                "output_dir": str(output_dir),
            },
        )


def _collect_via_lab_api(
    output_dir: Path,
    artifact_name: str,
) -> "List[pd.DataFrame]":
    """Fallback: traverse Experiment → Scenario → Run via the Lab object model.

    Uses :class:`~mas.lab.labs.Experiment` (backed by
    :class:`~mas.lab.benchmark.results.ExperimentResults`) to navigate the
    hierarchy and loads ``artifact_name`` from each run directory.

    Standard level columns (``scenario_id``, ``item_id``, ``run_id``) are
    added automatically.
    """
    import pandas as pd
    from mas.lab.benchmark.results import ExperimentResults

    frames: List[pd.DataFrame] = []

    try:
        exp = ExperimentResults.from_output_dir(output_dir)
        for sc in exp.scenarios:
            for item in sc.items:
                for rv in item.runs:
                    # Try parquet first, then CSV
                    for suffix in (".parquet", ".csv"):
                        candidate = rv.path / f"{artifact_name}{suffix}"
                        if candidate.exists():
                            try:
                                if suffix == ".parquet":
                                    df_part = pd.read_parquet(candidate)
                                else:
                                    df_part = pd.read_csv(candidate)
                                df_part = df_part.copy()
                                if "scenario_id" not in df_part.columns:
                                    df_part["scenario_id"] = sc.scenario_id
                                if "item_id" not in df_part.columns:
                                    df_part["item_id"] = item.item_id
                                if "run_id" not in df_part.columns:
                                    df_part["run_id"] = rv.run_id
                                frames.append(df_part)
                                break
                            except Exception as exc:
                                logger.warning(
                                    "gather_level: cannot read %s for run %s/%s/%s: %s",
                                    candidate, sc.scenario_id, item.item_id, rv.run_id, exc,
                                )
        logger.info(
            "gather_level: Lab API fallback — loaded %d parts from %d scenarios in %s",
            len(frames), len(exp.scenarios), output_dir,
        )
    except Exception as exc:
        logger.warning("gather_level: Lab API fallback failed at %s: %s", output_dir, exc)

    return frames
