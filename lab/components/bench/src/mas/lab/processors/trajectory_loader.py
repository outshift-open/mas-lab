#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Load a raw MAS trace into a :class:`~mas.lab.artifacts.Trajectory` artifact."""

from pathlib import Path
from typing import Any

from mas.lab.artifacts import Trajectory
from mas.lab.processor import Processor, register


@register
class TrajectoryLoader(Processor):
    """Load a JSONL trace file or run_id string into a Trajectory artifact.

    Accepted *artifact* types:

    * ``Trajectory`` with a ``path`` set — (re-)loads events from disk.
    * Any object with a ``path`` attribute.
    * A plain ``str`` or ``Path`` — treated as a JSONL file path or run_id.

    Config / kwargs
    ---------------
    run_id : str, optional
        Override the ``run_id`` stored on the resulting artifact.

    Examples
    --------
    ::

        loader = TrajectoryLoader()
        traj = loader.process("20260224-140201-baseline-e60feafd")
        traj = loader.process(Trajectory(path=Path("logs/events.jsonl")))
    """

    name        = "trajectory_loader"
    input_kind  = "path"          # special value — plain path/run_id, not an Artifact
    output_kind = "trajectory"
    description = "Load JSONL trace / run_id  →  Trajectory"

    def process(self, artifact: Any, **kwargs: Any) -> Trajectory:
        from mas.lab.plots.trajectory import load_trace

        if isinstance(artifact, Trajectory):
            source = artifact.path or artifact.data
            existing_meta = dict(artifact.meta)
        elif hasattr(artifact, "path") and artifact.path:
            source = artifact.path
            existing_meta = getattr(artifact, "meta", {})
        else:
            source = artifact
            existing_meta = {}

        events = load_trace(source)

        run_id = kwargs.get("run_id", "")
        if not run_id and isinstance(source, (str, Path)):
            run_id = Path(str(source)).stem   # best-effort

        # Build Trajectory — omit `meta` for compatibility with the legacy
        # mas.lab.artifacts.Trajectory (src/mas/lab) which lacks that field.
        try:
            return Trajectory(
                path=Path(str(source)) if isinstance(source, (str, Path)) else None,
                events=events,
                run_id=run_id,
                meta={**existing_meta},
            )
        except TypeError:
            return Trajectory(
                path=Path(str(source)) if isinstance(source, (str, Path)) else None,
                events=events,
                run_id=run_id,
            )

    def cli_options(self):
        return [
            {
                "param_decls": ["--run-id"],
                "default": None,
                "help": "Override the run_id stored on the resulting Trajectory.",
            }
        ]
