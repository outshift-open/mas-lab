#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""GatherLevelStep — concatenate child dataframe artifacts at this folder."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from mas.lab.benchmark.pipeline import PipelineStep, StepOutput

logger = logging.getLogger(__name__)


class GatherLevelStep(PipelineStep):
    """Concat CSV/parquet files listed in ``config["artifact_paths"]``."""

    type = "gather_level"

    async def execute(self, ctx: Any) -> StepOutput:
        import pandas as pd

        config = self.config
        paths = [Path(str(p)) for p in (config.get("artifact_paths") or [])]
        annotate: Dict[str, Any] = config.get("annotate") or {}
        fmt: str = config.get("format", "csv")

        frames: List["pd.DataFrame"] = []
        for path in paths:
            if not path.exists():
                logger.warning("gather_level '%s': missing %s", self.name, path)
                continue
            df_part = (
                pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
            )
            if df_part is None or df_part.empty:
                continue
            if annotate:
                df_part = df_part.copy()
                for col, val in annotate.items():
                    df_part[col] = val
            frames.append(df_part)

        if not frames:
            if paths:
                detail = (
                    f"none of {len(paths)} configured artifact_paths exist or "
                    f"contain data (checked {paths[0]}{', ...' if len(paths) > 1 else ''})"
                )
            else:
                detail = (
                    "config[\"artifact_paths\"] was empty — no child folders were "
                    "found for this level, or the `in:` artifact name didn't "
                    "resolve to anything the level below declares"
                )
            raise RuntimeError(
                f"gather_level '{self.name}': {detail} — fan-in produced nothing to concatenate."
            )

        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        output_dir = Path(config["output_dir"]) if config.get("output_dir") else ctx.output_dir
        output_path = Path(config.get("output", f"data.{fmt}"))
        if not output_path.is_absolute():
            output_path = output_dir / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "parquet":
            df.to_parquet(output_path, index=False)
        else:
            df.to_csv(output_path, index=False)

        return StepOutput(
            data={"df": df, "df_path": str(output_path), "rows": len(df)},
            files=[output_path],
            metadata={"rows": len(df), "parts": len(frames)},
        )
