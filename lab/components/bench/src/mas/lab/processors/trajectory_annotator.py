#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Annotate a :class:`~mas.lab.artifacts.Trajectory` with highlights and notes."""

from typing import Any, Dict, List

from mas.lab.artifacts import AnnotatedTrajectory, Trajectory
from mas.lab.processor import Processor, register


@register
class TrajectoryAnnotator(Processor):
    """Add highlights and free-form notes to a Trajectory.

    Produces an :class:`~mas.lab.artifacts.AnnotatedTrajectory` carrying the
    original events plus analyst-provided annotations.  The downstream
    :class:`~mas.lab.processors.trajectory_plotter.TrajectoryPlotter` renders
    these annotations as amber-highlighted arrows and tooltips.

    Config / kwargs
    ---------------
    highlights : list[str], optional
        Delegation identifiers to flag — each is either a correlation-id
        prefix or a 1-based index string.
    notes : list[dict], optional
        ``[{"index": 2, "note": "DB query missing index"}]``

    Examples
    --------
    ::

        annotator = TrajectoryAnnotator()
        atraj = annotator.process(
            traj,
            highlights=["f19445b6", "3"],
            notes=[{"index": 1, "note": "Slow telemetry fetch"}],
        )
    """

    name        = "trajectory_annotator"
    input_kind  = "trajectory"
    output_kind = "annotated_trajectory"
    description = "Trajectory + analyst markup  →  AnnotatedTrajectory"

    def process(
        self,
        artifact: Trajectory,
        highlights: List[str] | None = None,
        notes: List[Dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AnnotatedTrajectory:
        # Merge any annotations already on the artifact (e.g. if it's already
        # an AnnotatedTrajectory being re-annotated).
        existing_hl = list(getattr(artifact, "highlights", []))
        existing_notes = list(getattr(artifact, "notes", []))

        return AnnotatedTrajectory(
            path=artifact.path,
            events=list(artifact.events),
            run_id=getattr(artifact, "run_id", ""),
            meta=dict(artifact.meta),
            highlights=existing_hl + list(highlights or []),
            notes=existing_notes + list(notes or []),
        )

    def cli_options(self):
        return [
            {
                "param_decls": ["--highlight"],
                "multiple": True,
                "metavar": "CORR_OR_INDEX",
                "help": (
                    "Flag a delegation (amber).  Repeat for multiple.  "
                    "Accepts correlation-id prefix or 1-based index."
                ),
            },
            {
                "param_decls": ["--note"],
                "multiple": True,
                "metavar": "INDEX:TEXT",
                "help": "Attach a note to delegation INDEX (e.g. '2:Missing cache').",
            },
        ]
