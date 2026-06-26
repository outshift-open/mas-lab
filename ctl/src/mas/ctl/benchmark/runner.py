#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS bench integration — python-v2 kernel path for mas-lab benchmark."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mas.ctl.adapters.memory_seed import MemorySeed, MemorySeedLoader, apply_memory_seeds
from mas.ctl.infra.resolve import resolve_infra_refs
from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
from mas.ctl.session.controller import ConversationConfig, SessionController
from mas.ctl.ui.stdout import StdoutConversationDisplay
from mas.ctl.workspace.config import UserConfig, WorkspaceConfig, collect_mas_infra_refs, merge_infra_refs

logger = logging.getLogger(__name__)


@dataclass
class BenchRunResult:
    content: str
    status: str = "ok"
    error: str | None = None
    artifacts: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _resolve_ref(ref: str | Path, anchor: Path) -> Path:
    p = Path(ref)
    return p if p.is_absolute() else (anchor / p).resolve()


def _checkpoint_path(checkpoint_load: Any, anchor: Path) -> Path | None:
    if checkpoint_load is None:
        return None
    if isinstance(checkpoint_load, str):
        return _resolve_ref(checkpoint_load, anchor)
    if isinstance(checkpoint_load, dict):
        path_ref = checkpoint_load.get("path") or checkpoint_load.get("ref")
        if path_ref:
            return _resolve_ref(str(path_ref), anchor)
    return None


def _memory_seeds_from_run_input(
    memory_seeds: list[dict[str, Any]] | None,
) -> list[MemorySeed]:
    if not memory_seeds:
        return []
    return MemorySeedLoader.load_data(memory_seeds)


class MasBenchRunner:
    """Execute agent prompts via v2 SessionController (bench harness integration)."""

    runner_id: str = "mas-v2"

    def run(
        self,
        prompt: str,
        *,
        config: dict[str, Any],
        spec_path: Path,
        output_dir: Path,
        run_input: Any = None,
        run_seed: int = 0,
        infra_refs: list[str] | None = None,
        **kwargs: Any,
    ) -> BenchRunResult:
        from mas.lab.benchmark.runners.fixtures import write_tool_fixtures_sidecar
        from mas.lab.inputs import RunInput

        ri: RunInput | None = run_input if isinstance(run_input, RunInput) else None
        if ri is None and kwargs.get("run_input") is not None:
            candidate = kwargs["run_input"]
            if isinstance(candidate, RunInput):
                ri = candidate

        workspace = WorkspaceConfig.load(spec_path.parent)
        user = UserConfig.load()
        merged = merge_infra_refs(
            mas_refs=collect_mas_infra_refs(config),
            workspace_refs=workspace.effective_infra_refs,
            user_refs=[user.default_infra] if user.default_infra else [],
            cli_refs=list(infra_refs or []),
            workspace_found=workspace.found,
        )
        resolved = resolve_infra_refs(merged, anchor=spec_path.parent, workspace=workspace, user=user)

        queries = ri.scripted_queries() if ri else ([prompt] if prompt else [])
        if not queries:
            return BenchRunResult(content="", status="error", error="no user messages in run input")

        memory_seeds = _memory_seeds_from_run_input(ri.memory_seeds if ri else None)
        checkpoint_load = ri.checkpoint_load if ri else None
        checkpoint_save = bool(ri.checkpoint_save) if ri else False
        tool_fixtures = ri.tool_fixtures if ri else None

        write_tool_fixtures_sidecar(spec_path, tool_fixtures)

        checkpoint_path = _checkpoint_path(checkpoint_load, spec_path.parent)
        checkpoint_dir = output_dir / "checkpoints" if checkpoint_save else None

        instance, store = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=config,
                manifest_dir=spec_path.parent,
                resolved_infra=resolved,
                workspace=workspace,
                validate_manifests=False,
                checkpoint_path=checkpoint_path,
                checkpoint_dir=checkpoint_dir,
            ),
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        events_path = output_dir / "traces" / "events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)

        from mas.ctl.cli.obs_flags import resolve_observability_config
        from mas.ctl.session.observability import setup_observability
        from mas.ctl.session.controller import close_observability

        obs_cfg = resolve_observability_config(
            events=True,
            events_file=str(events_path),
            events_stdout=False,
            events_format="native",
            agent_id=str(config.get("metadata", {}).get("name", "agent")),
            manifest=config,
        )
        obs_rec = setup_observability(instance, obs_cfg, base_dir=output_dir)

        if memory_seeds:
            apply_memory_seeds(instance, memory_seeds)

        display = StdoutConversationDisplay(show_labels=False, verbose=0)
        controller = SessionController(
            instance=instance,
            display=display,
            obs_recorder=obs_rec,
            checkpoint_store=store,
            config=ConversationConfig(
                single_turn=len(queries) == 1,
                save_checkpoint_each_turn=checkpoint_save,
            ),
        )
        results = [controller.run_turn(q) for q in queries]
        close_observability(controller)

        if checkpoint_save and store is not None:
            final_path = store.save(instance.record_checkpoint("final"), label="final")
            logger.info("Saved final checkpoint: %s", final_path)

        text = results[-1].text if results else ""

        artifacts: list[dict[str, str]] = []
        if events_path.is_file() and events_path.stat().st_size > 0:
            artifacts.append(
                {
                    "kind": "events",
                    "path": str(events_path),
                    "agent_id": config.get("metadata", {}).get("name", ""),
                }
            )

        return BenchRunResult(
            content=text,
            status="ok",
            artifacts=artifacts,
            metadata={"run_seed": run_seed, "kernel": "python-v2", "turns": len(queries)},
        )


def select_mas_runner(*, runtime_id: str | None = None) -> MasBenchRunner:
    """Return the v2 bench runner."""
    _ = runtime_id
    return MasBenchRunner()
