#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unified lab runner factory — bench plugins and library extensions share one surface."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from mas.lab.runners.infer import infer_runner_id
from mas.lab.runners.protocol import ApplicationRunnerProtocol
from mas.lab.runners.registry import ApplicationRunnerRegistry


class RunnerFactory:
    """Request runners from all installed ``mas.lab.runners`` entry points."""

    @classmethod
    def available(cls) -> list[str]:
        ApplicationRunnerRegistry._ensure_initialized()
        return ApplicationRunnerRegistry.available()

    @classmethod
    def get(cls, runner_id: str) -> ApplicationRunnerProtocol:
        return ApplicationRunnerRegistry.get(runner_id)

    @classmethod
    def infer_and_get(
        cls,
        *,
        execution_runner: Optional[str] = None,
        mas_manifest: Optional[Path] = None,
        agent_config: Optional[dict[str, Any]] = None,
        flavour: Optional[Any] = None,
    ) -> ApplicationRunnerProtocol:
        runner_id = infer_runner_id(
            execution_runner=execution_runner,
            mas_manifest=mas_manifest,
            agent_config=agent_config,
            flavour=flavour,
        )
        return cls.get(runner_id)
