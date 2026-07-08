#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""JoinDataFrameStep — concatenate or merge multiple CSV dataframes.

Operations:
  - ``concat``: vertical stack (like pd.concat)
  - ``merge``: SQL-style join on key columns (like pd.merge)

Configuration
-------------
inputs       list[str]     Paths to input CSVs (supports globs).
operation    str            "concat" (default) or "merge".
on           str | list     Column(s) to merge on (required for merge).
how          str            Merge type: "inner", "left", "outer" (default: "inner").
output       str            Output CSV path.
add_source   bool           Add a ``_source`` column with the input filename (default: false).
filter       dict           Optional row filter: {column: value} or {column: [values]}.
select       list[str]      Optional column selection (keep only these columns).
sort_by      str | list     Optional sort columns.

Example YAML::

    - name: join
      type: join_dataframe
      config:
        inputs:
          - "{output_dir}/results.csv"
          - "{output_dir}/latency.csv"
        operation: merge
        on: [scenario, item_id, run_idx]
        output: "{output_dir}/combined.csv"
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput

logger = logging.getLogger(__name__)


class JoinDataFrameStep(PipelineStep):
    """Concatenate or merge multiple CSV dataframes."""

    type = "join_dataframe"

    async def execute(self, ctx: "ExecutionContext") -> StepOutput:
        import pandas as pd

        config = self.config

        # ── Resolve input files ────────────────────────────────────────
        raw_inputs: List[str] = config.get("inputs", [])
        if not raw_inputs:
            raise ValueError(f"JoinDataFrameStep '{self.name}': 'inputs' required")

        input_paths: List[Path] = []
        for pattern in raw_inputs:
            p = Path(pattern)
            if any(c in pattern for c in "*?["):
                # Glob pattern — resolve from an anchor directory
                if p.is_absolute():
                    # Find the first concrete parent (no wildcards)
                    parts = p.parts
                    concrete: list[str] = []
                    for part in parts:
                        if any(c in part for c in "*?["):
                            break
                        concrete.append(part)
                    root = Path(*concrete) if concrete else Path("/")
                    glob_rest = str(p.relative_to(root))
                    input_paths.extend(sorted(root.glob(glob_rest)))
                else:
                    input_paths.extend(sorted(Path.cwd().glob(pattern)))
            elif p.exists():
                input_paths.append(p)
            else:
                logger.warning("JoinDataFrameStep '%s': input not found: %s", self.name, p)

        if not input_paths:
            raise FileNotFoundError(f"JoinDataFrameStep '{self.name}': no input files found")

        # ── Read dataframes ────────────────────────────────────────────
        add_source = config.get("add_source", False)
        dfs: List[pd.DataFrame] = []
        for ip in input_paths:
            df = pd.read_csv(ip)
            if add_source:
                df["_source"] = ip.stem
            dfs.append(df)
            logger.debug("Read %d rows from %s", len(df), ip)

        # ── Operation ──────────────────────────────────────────────────
        operation = config.get("operation", "concat")

        if operation == "concat":
            result = pd.concat(dfs, ignore_index=True)
        elif operation == "merge":
            on_cols = config.get("on")
            if not on_cols:
                raise ValueError(f"JoinDataFrameStep '{self.name}': 'on' required for merge")
            if isinstance(on_cols, str):
                on_cols = [on_cols]
            how = config.get("how", "inner")
            # Coerce merge keys to string to prevent type mismatches
            for df in dfs:
                for col in on_cols:
                    if col in df.columns:
                        df[col] = df[col].astype(str)
            result = dfs[0]
            for df in dfs[1:]:
                result = result.merge(df, on=on_cols, how=how)
        else:
            raise ValueError(f"JoinDataFrameStep '{self.name}': unknown operation '{operation}'")

        # ── Filter ─────────────────────────────────────────────────────
        filter_spec = config.get("filter", {})
        for col, val in filter_spec.items():
            if isinstance(val, list):
                result = result[result[col].isin(val)]
            else:
                result = result[result[col] == val]

        # ── Select columns ─────────────────────────────────────────────
        select_cols = config.get("select")
        if select_cols:
            result = result[[c for c in select_cols if c in result.columns]]

        # ── Sort ───────────────────────────────────────────────────────
        sort_by = config.get("sort_by")
        if sort_by:
            if isinstance(sort_by, str):
                sort_by = [sort_by]
            result = result.sort_values(sort_by)

        # ── Write output ───────────────────────────────────────────────
        output_raw = config.get("output", "joined.csv")
        output_path = Path(output_raw)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)

        logger.info("JoinDataFrameStep '%s': %d rows → %s", self.name, len(result), output_path)
        return StepOutput(
            data={"rows": len(result), "csv_path": str(output_path)},
            files=[output_path],
            metadata={"output": str(output_path), "columns": list(result.columns)},
        )
