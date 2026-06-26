#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ApplicationRunner — pluggable lab execution façade.

The default ``mas`` backend wraps :mod:`mas.runtime` and :mod:`mas.ctl` **inside
the plugin implementation only**. The lab scheduler calls
:func:`mas.lab.runners.invoke.invoke_runner` with a :class:`RunContext`.
Alternative backends (langgraph, autogen, …) are not shipped in this repository;
OSS maps those adapter ids to the native ``mas`` runner. The default adapter is a
**bench plugin** (``mas.lab.benchmark.plugins.mas``) registered via the
``mas.lab.runners`` entry point.
"""
from __future__ import annotations

from mas.lab.runners.artifacts import ArtifactCollector
from mas.lab.runners.context import RunContext
from mas.lab.runners.factory import RunnerFactory
from mas.lab.runners.infer import infer_runner_id
from mas.lab.runners.invoke import invoke_runner
from mas.lab.runners.protocol import (
    ApplicationRunnerProtocol,
    RunResult,
)
from mas.lab.runners.registry import ApplicationRunnerRegistry

__all__ = [
    "ApplicationRunnerProtocol",
    "ApplicationRunnerRegistry",
    "ArtifactCollector",
    "RunContext",
    "RunResult",
    "RunnerFactory",
    "infer_runner_id",
    "invoke_runner",
]
