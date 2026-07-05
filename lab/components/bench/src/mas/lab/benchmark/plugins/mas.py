#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Native MAS machinery runner — thin lab adapter over :class:`MasBenchRunner`."""

import logging
from pathlib import Path
from typing import Any

from mas.lab.inputs import RunInput
from mas.lab.runners.constants import DEFAULT_LAB_RUNNER_ID
from mas.lab.runners.protocol import ApplicationRunnerProtocol, RunResult

logger = logging.getLogger(__name__)

_SUPPORTED_CONTRACTS = (
    "budget",
    "guardrail",
    "circuit_breaker",
    "session",
    "memory",
    "tool",
    "stats",
)


class MasRuntimeRunner(ApplicationRunnerProtocol):
    """Lab adapter delegating execution to :class:`mas.ctl.benchmark.runner.MasBenchRunner`."""

    runner_id: str = DEFAULT_LAB_RUNNER_ID

    def run(
        self,
        prompt: str,
        *,
        config: dict[str, Any],
        spec_path: Path,
        flavour: Any,
        output_dir: Path,
        run_input: RunInput | None = None,
        session_id: str | None = None,
        run_seed: int = 0,
        emulation_plugins: list | None = None,
        **kwargs: Any,
    ) -> RunResult:
        from mas.ctl.benchmark.runner import MasBenchRunner

        self._write_params_sidecar(config, output_dir)
        return MasBenchRunner().run(
            prompt,
            config=config,
            spec_path=spec_path,
            output_dir=output_dir,
            run_input=run_input or kwargs.get("run_input"),
            run_seed=run_seed,
            flavour=flavour,
            **kwargs,
        )

    def supports_contract(self, contract_id: str) -> bool:
        return contract_id in _SUPPORTED_CONTRACTS

    def get_supported_contracts(self) -> list[str]:
        return list(_SUPPORTED_CONTRACTS)

    @staticmethod
    def _write_params_sidecar(config: dict[str, Any], output_dir: Path) -> None:
        params = config.get("params") or {}
        if not params:
            return
        try:
            import yaml as _yaml

            sidecar_dir = output_dir / "artifacts"
            sidecar_dir.mkdir(parents=True, exist_ok=True)
            sidecar_path = sidecar_dir / "scene.yaml"
            with open(sidecar_path, "w", encoding="utf-8") as fh:
                _yaml.safe_dump(params, fh, default_flow_style=False, allow_unicode=True)
        except Exception as exc:
            logger.debug("Could not write params sidecar: %s", exc)
