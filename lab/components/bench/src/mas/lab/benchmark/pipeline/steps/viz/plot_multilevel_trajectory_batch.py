#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""PlotMultilevelTrajectoryBatchStep — batch version of PlotMultilevelTrajectoryStep.

Renders one multilevel trajectory diagram per run in a single pipeline step.

Can be wired either:
1. **Explicitly** — provide a ``runs`` list in config.
2. **From an extract_trajectories batch dependency** — items are auto-derived
   from the dependency's ``results`` output (each result carries
   ``trace_path`` / ``events_path`` and ``run_id``).

Config keys::

    runs : list (optional)
        Each entry may have:
            log_path  : str   Path to events.jsonl.  If omitted, resolved from
                              an extract_trajectories dependency.
            filename  : str   Output filename without extension.  Default: run_id.
            title     : str   Override per-diagram title.
    format : str
        Output format: ``html`` (default) or ``svg``.
    width_mode : str
        Column-width strategy: ``fixed`` | ``proportional`` | ``log`` (default).
    show_user_actors : bool
        Render person-icon user nodes (default: true).
    title : str
        Shared title prefix.  Per-run title = ``{title} — {run_id}``.
    concurrency : int
        Max parallel renders.  Default: 1 (sequential).

Example pipeline YAML::

    - name: extract-all
      type: extract_trajectories
      config:
        runs_dir: "{output_dir}"

    - name: multilevel-all
      type: plot_multilevel_trajectory_batch
      depends_on: [extract-all]
      config:
        format: html
        width_mode: log
        title: "Trip Planner — Multilevel Trajectory"
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from mas.lab.benchmark.pipeline import BatchPipelineStep, StepOutput
from mas.lab.benchmark.pipeline.executor import ExecutionContext

logger = logging.getLogger(__name__)


def _load_annotations(config: dict, pipeline_dir: "Path | None") -> "dict | None":
    """Resolve annotations for plot highlights.

    Priority (highest first):
    1. Inline ``highlight_agents`` / ``highlight_keywords`` keys in config.
    2. YAML file pointed to by the ``annotations`` key in config.

    The annotation YAML is resolved relative to the pipeline file directory
    when the path is not absolute.

    Example pipeline config::

        annotations: overlays/c3-annotations.yaml
        # or inline:
        highlight_agents: [telemetry, backend, db]
        highlight_keywords: [FLAGGED, inconclusive]
    """
    ann: dict = {}
    ann_path = config.get("annotations")
    if ann_path:
        import yaml
        p = Path(ann_path).expanduser()
        if not p.is_absolute() and pipeline_dir:
            p = (pipeline_dir / p).resolve()
        if p.exists():
            ann = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        else:
            logger.warning("annotations file not found: %s", p)
    # Inline keys take precedence over the file
    for key in ("highlight_agents", "pins"):
        if config.get(key) is not None:
            ann[key] = config[key]
    return ann or None


class PlotMultilevelTrajectoryBatchStep(BatchPipelineStep):
    """Render multilevel trajectory diagrams for multiple runs in one step."""

    type = "plot_multilevel_trajectory_batch"

    def _get_items(self, ctx: ExecutionContext) -> List[Dict[str, Any]]:
        # 1. Explicit runs list in config
        runs = self.config.get("runs", [])
        if runs:
            return runs

        # 2. Auto-derive from extract_trajectories dependency
        for dep_name in self.depends_on:
            dep_out = ctx.step_outputs.get(dep_name)
            if dep_out and "results" in dep_out.data:
                items = []
                for result in dep_out.data["results"]:
                    path_key = (
                        "events_path" if "events_path" in result
                        else "trace_path" if "trace_path" in result
                        else None
                    )
                    if path_key:
                        items.append({
                            "log_path": result[path_key],
                            "run_id":   result.get("run_id", ""),
                            "filename": result.get("run_id", "trajectory"),
                            "title":    result.get("session_label", result.get("run_id", "")),
                        })
                if items:
                    logger.info(
                        "Step '%s': derived %d items from dependency '%s'",
                        self.name, len(items), dep_name,
                    )
                    return items

        # 3. Auto-derive from extract_trajectories dependency via trajectories.jsonl.
        #
        # extract_trajectories outputs:  data={"trajectories_path": "/path/to/trajectories.jsonl"}
        # Each record in trajectories.jsonl carries "trace_path", "scenario", "run_id", etc.
        #
        # Config keys (all optional):
        #   filter_scenarios : list[str]  — only render traces for these scenario IDs.
        #   one_per_scenario : bool       — if true, take only the first matching run
        #                                   per scenario (good for paper figures).
        filter_scenarios = self.config.get("filter_scenarios") or None
        one_per_scenario = bool(self.config.get("one_per_scenario", False))

        for dep_name in self.depends_on:
            dep_out = ctx.step_outputs.get(dep_name)
            if dep_out and "trajectories_path" in dep_out.data:
                import json as _json
                traj_path = Path(dep_out.data["trajectories_path"])
                if not traj_path.exists():
                    logger.warning(
                        "Step '%s': trajectories.jsonl not found at %s (from dep '%s')",
                        self.name, traj_path, dep_name,
                    )
                    continue
                items: list[dict] = []
                seen_scenarios: set[str] = set()
                for line in traj_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        rec = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    scenario = rec.get("scenario", "")
                    if filter_scenarios and scenario not in filter_scenarios:
                        continue
                    if one_per_scenario:
                        if scenario in seen_scenarios:
                            continue
                        seen_scenarios.add(scenario)
                    trace_path = rec.get("trace_path", "")
                    if not trace_path or not Path(trace_path).exists():
                        continue
                    run_id = rec.get("run_id", "")
                    item_id = rec.get("item_id", "")
                    items.append({
                        "log_path": trace_path,
                        "run_id":   run_id,
                        "filename": run_id or f"{scenario}-{item_id}",
                        "title":    f"{scenario} — {item_id}",
                    })
                if items:
                    logger.info(
                        "Step '%s': derived %d items from trajectories.jsonl (dep '%s')",
                        self.name, len(items), dep_name,
                    )
                    return items

        raise ValueError(
            f"Step '{self.name}': no 'runs' in config and no compatible dependency found. "
            "Expected: 'runs' list in config, OR a normalize_events_batch dep with 'results', "
            "OR an extract_trajectories dep with 'trajectories_path'."
        )

    async def process_one(self, item: Dict[str, Any], ctx: ExecutionContext) -> StepOutput:
        from mas.lab.plots.trajectory import load_trace
        from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory

        fmt = str(self.config.get("format", "html")).lower()
        width_mode = str(self.config.get("width_mode", "log"))
        show_user_actors = bool(self.config.get("show_user_actors", True))
        base_title = self.config.get("title", "MAS Multilevel Trajectory")

        log_path: str = item.get("log_path", "")
        run_id: str = item.get("run_id", "")
        filename: str = item.get("filename", run_id or "trajectory")
        item_title: str = item.get("title") or (
            f"{base_title} — {run_id}" if run_id else base_title
        )

        if not log_path:
            raise ValueError(
                f"Step '{self.name}': each run entry must have a 'log_path'."
            )

        resolved = Path(log_path).expanduser()
        if not resolved.is_absolute():
            pipeline_dir = (
                ctx.pipeline.config_path.parent
                if ctx.pipeline is not None and getattr(ctx.pipeline, "config_path", None)
                else None
            )
            if pipeline_dir:
                candidate = (pipeline_dir / resolved).resolve()
                if candidate.exists():
                    resolved = candidate
        else:
            pipeline_dir = (
                ctx.pipeline.config_path.parent
                if ctx.pipeline is not None and getattr(ctx.pipeline, "config_path", None)
                else None
            )

        annotations = _load_annotations(self.config, pipeline_dir)

        events = load_trace(resolved)
        logger.info(
            "Step '%s' [%s]: loaded %d events from %s",
            self.name, run_id, len(events), resolved,
        )

        rendered = plot_multilevel_trajectory(
            events,
            fmt=fmt,
            title=item_title,
            width_mode=width_mode,
            show_user_actors=show_user_actors,
            annotations=annotations,
        )

        ext = ".html" if fmt == "html" else ".svg"
        output_dir = ctx.output_dir / "data" / self.name / "trajectories"
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{filename}{ext}"
        out_file.write_text(rendered, encoding="utf-8")

        logger.info(
            "Step '%s' [%s]: wrote %s (%d events, %d chars)",
            self.name, run_id, out_file, len(events), len(rendered),
        )

        return StepOutput(
            data={
                "trajectory_diagram": rendered,
                "format": fmt,
                "filename": filename,
                "run_id": run_id,
            },
            files=[out_file],
            metadata={
                "format": fmt,
                "events": len(events),
                "output_file": str(out_file),
                "title": item_title,
                "run_id": run_id,
            },
        )
