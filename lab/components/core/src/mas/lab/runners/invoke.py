#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Invoke a registered runtime plugin from a :class:`RunContext`."""
from __future__ import annotations

from mas.lab.runners.artifacts import ArtifactCollector
from mas.lab.runners.context import RunContext
from mas.lab.runners.factory import RunnerFactory
from mas.lab.runners.protocol import RunResult


def invoke_runner(ctx: RunContext) -> RunResult:
    """Run *ctx* through the runner factory and enrich artifacts from disk."""
    runner = RunnerFactory.get(ctx.runner_id)
    result = runner.run(ctx.prompt, **ctx.runner_kwargs())
    return ArtifactCollector.enrich(result, ctx.output_dir)
