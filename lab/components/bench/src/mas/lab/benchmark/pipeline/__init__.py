#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""
Pipeline system for declarative evaluation workflows.
"""


from mas.lab.benchmark.pipeline.cache import CacheManager
from mas.lab.benchmark.pipeline.core import (
    BatchPipelineStep,
    Pipeline,
    PipelineStep,
    YAMLIncludeLoader,
    include_constructor,
)
from mas.lab.benchmark.pipeline.models import (
    _CONFIG_KNOWN_KEYS,
    _MISSING,
    _STEP_KNOWN_KEYS,
    ArtifactSpec,
    ConfigParam,
    PipelineConfig,
    StepManifest,
    StepOutput,
)
from mas.lab.benchmark.pipeline.registry import (
    _CUSTOM_STEP_TYPES,
    get_step_registry,
    register_step_type,
)
from mas.lab.benchmark.pipeline.resolver import DependencyResolver
from mas.lab.benchmark.pipeline.steps import (
    AnalysisStep,
    DatasetStep,
    ExperimentStep,
    PlotStep,
)

_executor_exports = ("PipelineExecutor", "ExecutionContext", "ExecutionPlan")

__all__ = [
    "_MISSING",
    "_STEP_KNOWN_KEYS",
    "_CONFIG_KNOWN_KEYS",
    "_CUSTOM_STEP_TYPES",
    "ConfigParam",
    "Pipeline",
    "PipelineStep",
    "BatchPipelineStep",
    "StepManifest",
    "ArtifactSpec",
    "StepOutput",
    "PipelineConfig",
    "register_step_type",
    "get_step_registry",
    "YAMLIncludeLoader",
    "include_constructor",
    "PipelineExecutor",
    "ExecutionContext",
    "ExecutionPlan",
    "DependencyResolver",
    "CacheManager",
    "DatasetStep",
    "ExperimentStep",
    "AnalysisStep",
    "PlotStep",
]


def __getattr__(name: str):
    if name in _executor_exports:
        from mas.lab.benchmark.pipeline.executor import (
            ExecutionContext,
            ExecutionPlan,
            PipelineExecutor,
        )

        import sys

        _mod = sys.modules[__name__]
        _mod.PipelineExecutor = PipelineExecutor
        _mod.ExecutionContext = ExecutionContext
        _mod.ExecutionPlan = ExecutionPlan
        return locals()[name]
    raise AttributeError(f"module 'mas.lab.benchmark.pipeline' has no attribute {name!r}")
