#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Lab package — MAS run configurations for interactive demo and batch experiment.

Two concrete run types share a common base (``MASRunBase``):

- ``LabConfig``           / lab-config.yaml    →  MAS live UI, one run at a time
- ``MASExperimentConfig`` / mas-experiment.yaml →  MAS batch benchmarking

Both share EvaluationSpec and dataset conventions from the benchmark package.
"""

from .config import (
    LabConfig,
    MASRunBase,
    MASSpec,
    MASScenarioSpec,
    UISpec,
    MASExecutionSpec,
    MASExperimentConfig,
    PipelineStepSpec,
    discover_scenario_stems,
    load_scenario_config,
    load_stacked_config,
)

__all__ = [
    "LabConfig",
    "MASRunBase",
    "MASSpec",
    "MASScenarioSpec",
    "UISpec",
    "MASExecutionSpec",
    "MASExperimentConfig",
    "PipelineStepSpec",
    "discover_scenario_stems",
    "load_scenario_config",
    "load_stacked_config",
]
