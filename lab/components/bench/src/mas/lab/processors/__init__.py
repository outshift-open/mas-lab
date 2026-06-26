#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""Built-in processors for the mas-lab benchmark library.

Importing this package registers all processors in the global
:mod:`mas.lab.processor` registry.  This happens automatically when
the CLI calls ``mas-lab run processor`` or when a pipeline step of
``type: processor`` is executed.

Built-in processors
-------------------
trajectory_loader
    Load a JSONL trace or run_id  →  Trajectory
trajectory_annotator
    Add highlights and notes to a Trajectory  →  AnnotatedTrajectory
trajectory_plotter
    Render a (Annotated)Trajectory to HTML/SVG/Mermaid via Mermaid+playwright  →  PlotFile (priority=1)
trajectory_plotter_native
    Same as above but uses the hand-drawn Python SVG renderer (no playwright)  →  PlotFile (priority=10)
multilevel_trajectory_plotter
    Render a multilevel lane diagram (Session/MAS/Agent/Call) from a JSONL trace  →  PlotFile (priority=1)
communication-flow-plotter
    Render an agent-to-agent message routing graph (force/hierarchical/circular)  →  PlotFile (priority=1)
    [registered via mas.lab.plots.communication_flow; import mas.lab.plots to activate]

Adding a local processor
------------------------
Create a module that defines a ``Processor`` subclass decorated with
``@register``, then import it in your pipeline config or Python code::

    # my_project/processors/my_processor.py
    from mas.lab.processor import Processor, register

    @register
    class MyProcessor(Processor):
        name        = "my_processor"
        input_kind  = "trajectory"
        output_kind = "plot_file"
        description = "Experimental processor"

        def process(self, artifact, **kwargs):
            ...

    # In your experiment script or pipeline step:
    import my_project.processors.my_processor  # triggers @register
"""

from mas.lab.processors.trajectory_loader          import TrajectoryLoader
from mas.lab.processors.trajectory_annotator       import TrajectoryAnnotator
from mas.lab.processors.trajectory_plotter         import TrajectoryPlotter
from mas.lab.processors.trajectory_plotter_native  import TrajectoryPlotterNative
from mas.lab.plots.multilevel_trajectory_processor import MultilevelTrajectoryPlotter
from mas.lab.plots.communication_flow              import CommunicationFlowPlotter

__all__ = [
    "TrajectoryLoader",
    "TrajectoryAnnotator",
    "TrajectoryPlotter",
    "TrajectoryPlotterNative",
    "MultilevelTrajectoryPlotter",
    "CommunicationFlowPlotter",
]
