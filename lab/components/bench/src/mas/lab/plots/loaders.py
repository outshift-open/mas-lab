#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Source processors — load artifacts from disk for use as pipeline inputs.

These processors accept ``None`` as their first argument (they are *sources*)
and produce a typed artifact that subsequent pipeline stages can consume.

Registered elements
-------------------
``trajectory-loader``
    Loads a :class:`~mas.lab.artifacts.Trajectory` from a ``events.jsonl``
    file path or a run-id string.  Use this as the first element in any pipe
    that feeds into a plot processor::

        mas-lab pipe run trajectory-loader path=runs/.../events.jsonl \\
            ! multilevel-trajectory-plotter fmt=html output=out.html
"""

from pathlib import Path
from typing import Any

from mas.lab.artifacts import Trajectory
from mas.lab.processor import Processor, ParamDef, register


@register
class TrajectoryLoader(Processor):
    """Load a MAS execution trace from disk.

    This is a *source* element: it ignores its input artifact and produces a
    :class:`~mas.lab.artifacts.Trajectory` ready for downstream processors.

    Parameters
    ----------
    path : str
        Path to an ``events.jsonl`` file.  Mutually exclusive with *run_id*.
    run_id : str
        Benchmark run-id (resolved from :func:`mas.lab.paths.runs_root`).
        Mutually exclusive with *path*.
    """

    name        = "trajectory-loader"
    input_kind  = ""            # source — no upstream artifact required
    output_kind = "trajectory"
    description = "Load a trajectory from an events.jsonl path or run-id"
    priority    = 0             # always first

    params = [
        ParamDef(
            name="path",
            type="str",
            required=False,
            description="Path to events.jsonl file.",
        ),
        ParamDef(
            name="run_id",
            type="str",
            required=False,
            description="Benchmark run-id (resolved from mas.lab.paths.runs_root()).",
        ),
    ]

    def process(self, artifact: Any, **kwargs: Any) -> Trajectory:  # type: ignore[override]
        path_raw  = kwargs.get("path")
        run_id    = kwargs.get("run_id")

        if not path_raw and not run_id:
            raise ValueError(
                "trajectory-loader requires either path= or run_id= parameter."
            )

        traj = Trajectory(
            path=Path(path_raw) if path_raw else None,
            run_id=run_id or None,
        )
        traj.load()
        return traj
