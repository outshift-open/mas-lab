#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Native MAS machinery runner — default lab adapter plugin (mas-lab-bench)."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mas.lab.inputs import RunInput
from mas.lab.runners.constants import DEFAULT_LAB_RUNNER_ID
from mas.lab.runners.protocol import ApplicationRunnerProtocol, RunResult
from mas.runtime.run_artifact import RunArtifact

logger = logging.getLogger(__name__)


class MasRuntimeRunner(ApplicationRunnerProtocol):
    """Lab adapter delegating to :class:`mas.ctl.benchmark.runner.MasBenchRunner`."""

    runner_id: str = DEFAULT_LAB_RUNNER_ID

    def run(
        self,
        prompt: str,
        *,
        config: Dict[str, Any],
        spec_path: Path,
        flavour: Any,
        output_dir: Path,
        run_input: Optional[RunInput] = None,
        session_id: Optional[str] = None,
        run_seed: int = 0,
        emulation_plugins: Optional[List] = None,
        **kwargs: Any,
    ) -> RunResult:
        from mas.ctl.benchmark.runner import MasBenchRunner
        from mas.ctl.deployment.runtime_id import DEFAULT_RUNTIME_ID
        from mas.lab.manifest.load import load_agent_for_bench
        from mas.ctl.runtime_cli import load_merged_agent_manifest

        self._write_params_sidecar(config, spec_path)

        overlay_paths = [Path(p) for p in (kwargs.get("overlay_paths") or []) if p]
        agent_cfg: dict[str, Any]
        agent_path: Path
        if str(config.get("kind", "")).lower() == "agent":
            if overlay_paths:
                agent_cfg, agent_path = load_agent_for_bench(
                    spec_path, overlay_paths=overlay_paths
                )
            else:
                agent_cfg = config
                agent_path = spec_path
        elif spec_path.name in ("mas.yaml", "mas.yml") or (
            spec_path.parent / "mas.yaml"
        ).is_file():
            mas_path = (
                spec_path
                if spec_path.name.startswith("mas.")
                else spec_path.parent / "mas.yaml"
            )
            agent_cfg, agent_path = load_agent_for_bench(
                mas_path, overlay_paths=overlay_paths or None
            )
        else:
            if overlay_paths:
                agent_cfg, agent_path = load_agent_for_bench(
                    spec_path, overlay_paths=overlay_paths
                )
            else:
                agent_path = spec_path
                agent_cfg, _ = load_merged_agent_manifest(spec_path, validate=False)

        _spec = agent_cfg.get("spec") or {}
        _infra = list(kwargs.get("infra_refs") or [])
        if not _infra:
            _infra = list(_spec.get("infra_refs") or [])

        ri = run_input
        if ri is None and kwargs.get("run_input") is not None:
            candidate = kwargs["run_input"]
            if isinstance(candidate, RunInput):
                ri = candidate

        bench_result = MasBenchRunner().run(
            prompt,
            config=agent_cfg,
            spec_path=agent_path,
            output_dir=output_dir,
            run_input=ri,
            run_seed=run_seed,
            infra_refs=_infra,
        )
        artifacts = [
            RunArtifact(
                kind=a["kind"],
                path=Path(a["path"]) if a.get("path") else None,
                meta={"agent_id": a.get("agent_id", "")},
            )
            for a in bench_result.artifacts
        ]
        return RunResult(
            content=bench_result.content,
            status=bench_result.status if bench_result.status in ("ok", "error") else "ok",
            error=bench_result.error,
            artifacts=artifacts,
            metadata={
                **bench_result.metadata,
                "runtime_id": DEFAULT_RUNTIME_ID,
                "run_seed": run_seed,
                "adapter_plugin": "mas-lab-bench.plugins.mas",
            },
        )

    def supports_contract(self, contract_id: str) -> bool:
        return contract_id in {
            "budget",
            "guardrail",
            "circuit_breaker",
            "session",
            "memory",
            "tool",
            "stats",
        }

    def get_supported_contracts(self) -> List[str]:
        return [
            "budget",
            "guardrail",
            "circuit_breaker",
            "session",
            "memory",
            "tool",
            "stats",
        ]

    @staticmethod
    def _write_params_sidecar(config: Dict[str, Any], spec_path: Path) -> None:
        params = config.get("params") or {}
        if not params:
            return
        try:
            import yaml as _yaml

            sidecar_dir = spec_path.parent / "artifacts"
            sidecar_dir.mkdir(parents=True, exist_ok=True)
            sidecar_path = sidecar_dir / "scene.yaml"
            with open(sidecar_path, "w", encoding="utf-8") as fh:
                _yaml.safe_dump(params, fh, default_flow_style=False, allow_unicode=True)
        except Exception as exc:
            logger.debug("Could not write params sidecar: %s", exc)
