#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS bench integration — default ctl runtime path for mas-lab benchmark."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mas.ctl.adapters.memory_seed import MemorySeed, MemorySeedLoader, apply_memory_seeds
from mas.ctl.benchmark.runner_dispatch import mas_manifest_path
from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.compose.runner import ComposeRequest, ComposeResult, compose_run
from mas.ctl.deployment.runtime_id import DEFAULT_RUNTIME_ID
from mas.ctl.paths import OverlayRefEntry, resolve_overlay_ref_entries
from mas.ctl.executor.mas_session import (
    agent_manifest_label,
    entry_agent_id,
    is_sequential_workflow,
    materialize_mas_compose,
    prepare_delegation_entry_session,
    resolve_entry_pattern_plugin_id,
    run_sequential_workflow_queries,
)
from mas.ctl.infra.resolve import resolve_infra_refs
from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
from mas.ctl.session.controller import ConversationConfig, SessionController, close_observability
from mas.ctl.workspace.config import UserConfig, WorkspaceConfig, collect_mas_infra_refs, merge_infra_refs
from mas.lab.manifest.load import (
    agent_manifest_from_path,
    entry_agent_from_compose,
    is_loaded_mas_raw,
    merge_stacked_entry_agent_manifest,
    should_merge_stacked_entry_agent_config,
)
from mas.lab.runners.constants import DEFAULT_LAB_RUNNER_ID
from mas.lab.runners.protocol import RunResult
from mas.runtime.run_artifact import RunArtifact

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ControllerTarget:
    instance: Any
    store: Any
    manifest: dict[str, Any]
    manifest_path: Path
    topology: str | None = None
    obs_recorder: Any = None
    obs_pipeline: Any = None


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


def _manifest_kind_on_disk(spec_path: Path) -> str:
    from mas.runtime.spec.source import load_yaml_mapping

    try:
        doc = load_yaml_mapping(spec_path)
    except (FileNotFoundError, OSError):
        return ""
    return str((doc or {}).get("kind", "")).lower()


def _manifest_with_flavour_observability(
    manifest: dict[str, Any],
    flavour: Any,
) -> dict[str, Any]:
    """Overlay flavour ``spec.observability`` onto *manifest* for bench runs."""
    if not flavour or not isinstance(flavour, dict):
        return manifest
    fl_spec = flavour.get("spec")
    if not isinstance(fl_spec, dict):
        fl_spec = flavour
    fl_obs = fl_spec.get("observability")
    if not fl_obs:
        return manifest
    merged = dict(manifest)
    spec = dict(merged.get("spec") or {})
    spec["observability"] = list(fl_obs) if isinstance(fl_obs, list) else fl_obs
    merged["spec"] = spec
    return merged


def bench_obs_config(
    output_dir: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
    *,
    mas_config: dict[str, Any] | None = None,
    flavour: Any = None,
) -> tuple[Path, Any]:
    """Return ``(events_path, obs_cfg)`` for one bench run output dir."""
    from mas.ctl.cli.obs_flags import resolve_observability_config
    from mas.ctl.session.manifest_config import mas_id_from_manifest

    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "traces" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    mas_id = mas_id_from_manifest(mas_config) if mas_config else mas_id_from_manifest(manifest)
    effective_manifest = _manifest_with_flavour_observability(manifest, flavour)
    obs_cfg = resolve_observability_config(
        events=True,
        events_file=str(events_path),
        events_stdout=False,
        events_format=None,
        agent_id=agent_manifest_label(manifest, manifest_path),
        mas_id=mas_id,
        manifest=effective_manifest,
    )
    return events_path, obs_cfg


def _events_artifacts(events_path: Path, manifest: dict[str, Any], manifest_path: Path) -> list[RunArtifact]:
    if events_path.is_file() and events_path.stat().st_size > 0:
        return [
            RunArtifact(
                kind="events",
                path=events_path,
                meta={"agent_id": agent_manifest_label(manifest, manifest_path)},
            )
        ]
    return []


def ensure_live_otel_span_files(events_path: Path, obs_cfg: Any) -> None:
    """Backfill otel/observe JSONL span exports from events.jsonl when missing."""
    import logging

    logger = logging.getLogger(__name__)
    plugins = list(getattr(obs_cfg, "plugins", None) or [])
    norm = {(p or "").split("@")[0].replace("-", "_") for p in plugins}
    if not norm.intersection({"otel", "observe_sdk", "ioa_observe"}):
        return
    if not events_path.is_file() or events_path.stat().st_size == 0:
        return

    traces_dir = events_path.parent
    targets: list[Path] = []
    if "otel" in norm:
        targets.append(traces_dir / "otel_sdk_spans.jsonl")
    if norm.intersection({"observe_sdk", "ioa_observe"}):
        targets.append(traces_dir / "observe_sdk_spans.jsonl")

    try:
        from mas.library.standard.lib.observability.export_layers import parse_export_layers
        from mas.library.standard.lib.observability.otel.converter import (
            OTEL_AVAILABLE,
            MasOtelConverter,
        )
    except ImportError:
        return
    if not OTEL_AVAILABLE:
        return

    otel_cfg = (getattr(obs_cfg, "plugin_configs", None) or {}).get("otel") or {}
    service_name = str(getattr(obs_cfg, "mas_id", "") or getattr(obs_cfg, "agent_id", "") or "mas-runtime")
    layers = parse_export_layers(otel_cfg)

    def _span_line_count(path: Path) -> int:
        if not path.is_file() or path.stat().st_size == 0:
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    for dest in targets:
        live_count = _span_line_count(dest)
        if live_count > 0:
            # Live plugin already wrote spans — don't overwrite.
            logger.debug("Span export already present (%d spans): %s", live_count, dest)
            continue
        try:
            MasOtelConverter.replay_file(
                events_path,
                dest,
                service_name=service_name,
                app_name=service_name,
                export_layers=layers,
            )
            logger.info("Backfilled span export: %s (%d spans)", dest, _span_line_count(dest))
        except Exception:
            logger.warning("Failed to materialize span export %s", dest, exc_info=True)


def _default_observability_overlay_path() -> Path:
    """Canonical ``observability-native`` overlay shipped with library-standard."""
    import mas.library.standard as std_pkg

    return (Path(std_pkg.__file__).resolve().parent / "overlays" / "observability-native.yaml")


def _ensure_observability_overlay(overlay_paths: list[Path]) -> list[Path]:
    """Prepend observability-native overlay so lab/bench runs are always instrumented."""
    obs = _default_observability_overlay_path()
    if not obs.is_file():
        return overlay_paths
    resolved = obs.resolve()
    if any(p.resolve() == resolved for p in overlay_paths):
        return overlay_paths
    return [resolved, *overlay_paths]


def _resolve_overlay_paths(
    overlay_refs: list[OverlayRefEntry],
    *,
    manifest_path: Path,
    overlays_dir: Path | None = None,
    base_dir: Path | None = None,
) -> list[Path]:
    if not overlay_refs:
        return []
    return list(
        resolve_overlay_ref_entries(
            overlay_refs,
            manifest_dir=manifest_path.parent,
            overlays_dir=overlays_dir,
            base_dir=base_dir,
        )
    )


class MasBenchRunner:
    """Execute agent prompts via v2 SessionController (bench harness integration)."""

    runner_id: str = DEFAULT_LAB_RUNNER_ID

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
        mas_path: Path | None = None,
        overlay_refs: list[OverlayRefEntry] | None = None,
        overlays_dir: Path | None = None,
        overlay_base_dir: Path | None = None,
        flavour: Any = None,
        **kwargs: Any,
    ) -> RunResult:
        from mas.lab.benchmark.runners.fixtures import write_tool_fixtures_sidecar
        from mas.lab.inputs import RunInput

        ri: RunInput | None = run_input if isinstance(run_input, RunInput) else None

        queries = ri.scripted_queries() if ri else ([prompt] if prompt else [])
        if not queries:
            return RunResult(content="", status="error", error="no user messages in run input")

        memory_seeds = _memory_seeds_from_run_input(ri.memory_seeds if ri else None)
        checkpoint_load = ri.checkpoint_load if ri else None
        checkpoint_save = bool(ri.checkpoint_save) if ri else False
        tool_fixtures = ri.tool_fixtures if ri else None

        write_tool_fixtures_sidecar(spec_path, tool_fixtures)

        checkpoint_path = _checkpoint_path(checkpoint_load, spec_path.parent)
        checkpoint_dir = output_dir / "checkpoints" if checkpoint_save else None

        _infra = list(infra_refs or [])
        if not _infra:
            _infra = list((config.get("spec") or {}).get("infra_refs") or [])
        _overlay_refs: list[OverlayRefEntry] = list(overlay_refs or [])
        _overlays_dir = overlays_dir
        _overlay_base = overlay_base_dir

        resolved = self._resolve_target(
            config=config,
            spec_path=spec_path,
            mas_path=mas_path,
            overlay_refs=_overlay_refs,
            overlays_dir=_overlays_dir,
            overlay_base_dir=_overlay_base,
            infra_refs=_infra,
            memory_seeds=memory_seeds,
            checkpoint_path=checkpoint_path,
            checkpoint_dir=checkpoint_dir,
            checkpoint_save=checkpoint_save,
            queries=queries,
            output_dir=output_dir,
            run_seed=run_seed,
            flavour=flavour,
        )
        if isinstance(resolved, RunResult):
            return self._with_bench_metadata(resolved, run_seed=run_seed)

        result = self._run_controller_turns(
            instance=resolved.instance,
            store=resolved.store,
            config=resolved.manifest,
            spec_path=resolved.manifest_path,
            output_dir=output_dir,
            queries=queries,
            memory_seeds=memory_seeds,
            checkpoint_save=checkpoint_save,
            run_seed=run_seed,
            topology=resolved.topology,
            obs_recorder=resolved.obs_recorder,
            obs_pipeline=resolved.obs_pipeline,
            flavour=flavour,
        )
        return self._with_bench_metadata(result, run_seed=run_seed)

    @staticmethod
    def _with_bench_metadata(result: RunResult, *, run_seed: int) -> RunResult:
        meta = dict(result.metadata)
        meta.setdefault("runtime_id", DEFAULT_RUNTIME_ID)
        meta.setdefault("run_seed", run_seed)
        meta.setdefault("adapter_plugin", "mas-lab-bench.plugins.mas")
        if result.metadata == meta:
            return result
        return RunResult(
            content=result.content,
            status=result.status,
            error=result.error,
            artifacts=result.artifacts,
            metadata=meta,
        )

    def _resolve_target(
        self,
        *,
        config: dict[str, Any],
        spec_path: Path,
        mas_path: Path | None,
        overlay_refs: list[OverlayRefEntry],
        overlays_dir: Path | None,
        overlay_base_dir: Path | None,
        infra_refs: list[str],
        memory_seeds: list[MemorySeed],
        checkpoint_path: Path | None,
        checkpoint_dir: Path | None,
        checkpoint_save: bool,
        queries: list[str],
        output_dir: Path,
        run_seed: int,
        flavour: Any = None,
    ) -> RunResult | _ControllerTarget:
        entry_manifest = config
        entry_manifest_path = spec_path

        resolved_mas_path = mas_path or mas_manifest_path(config, spec_path)
        if resolved_mas_path is None:
            has_oasf_doc = isinstance(config.get("metadata"), dict) and isinstance(
                config.get("spec"), dict
            )
            if _manifest_kind_on_disk(spec_path) == "agent" and (
                is_loaded_mas_raw(config) or not has_oasf_doc
            ):
                entry_manifest, entry_manifest_path = agent_manifest_from_path(
                    spec_path,
                    overlay_refs=overlay_refs,
                    overlays_dir=overlays_dir,
                    overlay_base_dir=overlay_base_dir,
                )
            elif str(config.get("kind", "")).lower() == "agent" and not has_oasf_doc:
                entry_manifest, entry_manifest_path = agent_manifest_from_path(
                    spec_path,
                    overlay_refs=overlay_refs,
                    overlays_dir=overlays_dir,
                    overlay_base_dir=overlay_base_dir,
                )
            if should_merge_stacked_entry_agent_config(config):
                entry_manifest = merge_stacked_entry_agent_manifest(entry_manifest, config)
            return self._standalone_controller_target(
                entry_manifest=entry_manifest,
                entry_manifest_path=entry_manifest_path,
                infra_refs=infra_refs,
                checkpoint_path=checkpoint_path,
                checkpoint_dir=checkpoint_dir,
            )

        overlay_paths = _ensure_observability_overlay(
            _resolve_overlay_paths(
                overlay_refs,
                manifest_path=resolved_mas_path,
                overlays_dir=overlays_dir,
                base_dir=overlay_base_dir,
            )
        )
        compose = compose_run(
            ComposeRequest(
                manifest=resolved_mas_path,
                overlay_paths=overlay_paths,
                infra_refs=infra_refs,
                validate=False,
            )
        )
        entry_manifest, entry_manifest_path = entry_agent_from_compose(compose, resolved_mas_path)
        if should_merge_stacked_entry_agent_config(config):
            entry_manifest = merge_stacked_entry_agent_manifest(entry_manifest, config)

        bind = compose.bind
        entry = entry_agent_id(compose.mas_config)

        if len(bind.agents) <= 1:
            pattern_plugin_id = resolve_entry_pattern_plugin_id(
                compose, entry, entry_manifest=entry_manifest
            )
            instance, store = instantiate_runtime(
                InstantiationOptions(
                    agent_manifest=entry_manifest,
                    manifest_dir=entry_manifest_path.parent,
                    resolved_infra=compose.resolved_infra or ResolvedInfra(),
                    workspace=WorkspaceConfig.load(resolved_mas_path.parent),
                    validate_manifests=False,
                    checkpoint_path=checkpoint_path,
                    checkpoint_dir=checkpoint_dir,
                    pattern_plugin_id=pattern_plugin_id,
                ),
            )
            return _ControllerTarget(instance, store, entry_manifest, entry_manifest_path)

        materialized = materialize_mas_compose(compose, mas_base_dir=resolved_mas_path.parent)

        if is_sequential_workflow(compose.mas_config, len(bind.agents)):
            return self._run_sequential_with_observability(
                materialized=materialized,
                queries=queries,
                output_dir=output_dir,
                entry_manifest=entry_manifest,
                entry_manifest_path=entry_manifest_path,
                run_seed=run_seed,
                memory_seeds=memory_seeds,
                flavour=flavour,
            )

        try:
            events_path, obs_cfg = bench_obs_config(
                output_dir,
                entry_manifest,
                entry_manifest_path,
                mas_config=compose.mas_config,
                flavour=flavour,
            )
            from mas.ctl.session.observability import create_shared_observability

            shared_pipeline, obs_setup_fn = create_shared_observability(
                obs_cfg, base_dir=output_dir
            )
            try:
                prepared = prepare_delegation_entry_session(
                    materialized,
                    entry_id=entry,
                    entry_manifest=entry_manifest,
                    entry_manifest_path=entry_manifest_path,
                    display=None,
                    verbose=0,
                )
            except KeyError:
                if shared_pipeline is not None:
                    shared_pipeline.close()
                raise
        except KeyError as exc:
            logger.error("Run failed: %s", exc, exc_info=True)
            return RunResult(content="", status="error", error=str(exc))

        store = self._checkpoint_store(checkpoint_dir, checkpoint_path)
        if checkpoint_path is not None and checkpoint_path.is_file() and store is not None:
            prepared.instance.load_checkpoint(store.load(checkpoint_path))

        obs_rec = obs_setup_fn(prepared.instance, entry) if obs_setup_fn is not None else None

        return _ControllerTarget(
            prepared.instance,
            store,
            prepared.enriched_manifest,
            prepared.manifest_path,
            topology="delegation",
            obs_recorder=obs_rec,
            obs_pipeline=shared_pipeline,
        )

    def _standalone_controller_target(
        self,
        *,
        entry_manifest: dict[str, Any],
        entry_manifest_path: Path,
        infra_refs: list[str],
        checkpoint_path: Path | None,
        checkpoint_dir: Path | None,
    ) -> _ControllerTarget:
        workspace = WorkspaceConfig.load(entry_manifest_path.parent)
        user = UserConfig.load()
        merged = merge_infra_refs(
            mas_refs=collect_mas_infra_refs(entry_manifest),
            workspace_refs=workspace.effective_infra_refs,
            user_refs=[user.default_infra] if user.default_infra else [],
            cli_refs=list(infra_refs or []),
            workspace_found=workspace.found,
        )
        resolved = resolve_infra_refs(
            merged, anchor=entry_manifest_path.parent, workspace=workspace, user=user
        )
        entry_id = agent_manifest_label(entry_manifest, entry_manifest_path)
        pattern_plugin_id = resolve_entry_pattern_plugin_id(
            None, entry_id, entry_manifest=entry_manifest
        )
        instance, store = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=entry_manifest,
                manifest_dir=entry_manifest_path.parent,
                resolved_infra=resolved,
                workspace=workspace,
                validate_manifests=False,
                checkpoint_path=checkpoint_path,
                checkpoint_dir=checkpoint_dir,
                pattern_plugin_id=pattern_plugin_id,
            ),
        )
        return _ControllerTarget(instance, store, entry_manifest, entry_manifest_path)

    def _run_sequential_with_observability(
        self,
        *,
        materialized,
        queries: list[str],
        output_dir: Path,
        entry_manifest: dict[str, Any],
        entry_manifest_path: Path,
        run_seed: int,
        memory_seeds: list[MemorySeed],
        flavour: Any = None,
    ) -> RunResult:
        from mas.ctl.session.observability import create_shared_observability
        from mas.ctl.ui.stdout import StdoutConversationDisplay

        if memory_seeds:
            for instance in materialized.materialized.instances.values():
                apply_memory_seeds(instance, memory_seeds)

        events_path, obs_cfg = bench_obs_config(
            output_dir,
            entry_manifest,
            entry_manifest_path,
            mas_config=materialized.compose.mas_config,
            flavour=flavour,
        )
        pipeline, obs_setup_fn = create_shared_observability(obs_cfg, base_dir=output_dir)

        display = StdoutConversationDisplay(show_labels=False, verbose=0)
        try:
            text = run_sequential_workflow_queries(
                materialized.compose.mas_config,
                materialized,
                queries,
                display=display,
                verbose=0,
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            # Surface the real cause by default — never require LOG_LEVEL=DEBUG to
            # see why a run failed. The full traceback goes to the log at ERROR
            # (visible at default verbosity); the summary is kept on the result.
            logger.error("Run failed: %s", exc, exc_info=True)
            return RunResult(content="", status="error", error=str(exc))
        finally:
            if pipeline is not None:
                pipeline.close()
            ensure_live_otel_span_files(events_path, obs_cfg)

        return RunResult(
            content=text,
            status="ok",
            artifacts=_events_artifacts(events_path, entry_manifest, entry_manifest_path),
            metadata={"run_seed": run_seed, "turns": len(queries), "topology": "sequential"},
        )

    @staticmethod
    def _checkpoint_store(
        checkpoint_dir: Path | None,
        checkpoint_path: Path | None,
    ):
        from mas.ctl.adapters.checkpoint import JsonCheckpointStore

        if checkpoint_dir is not None:
            return JsonCheckpointStore(checkpoint_dir)
        if checkpoint_path is not None:
            return JsonCheckpointStore(checkpoint_path.parent)
        return None

    def _run_controller_turns(
        self,
        *,
        instance: Any,
        store: Any,
        config: dict[str, Any],
        spec_path: Path,
        output_dir: Path,
        queries: list[str],
        memory_seeds: list[MemorySeed],
        checkpoint_save: bool,
        run_seed: int,
        topology: str | None = None,
        obs_recorder: Any = None,
        obs_pipeline: Any = None,
        flavour: Any = None,
    ) -> RunResult:
        from mas.ctl.session.observability import setup_observability
        from mas.ctl.ui.stdout import StdoutConversationDisplay

        events_path, obs_cfg = bench_obs_config(
            output_dir, config, spec_path, flavour=flavour
        )
        obs_rec = obs_recorder if obs_recorder is not None else setup_observability(
            instance, obs_cfg, base_dir=output_dir
        )

        if memory_seeds:
            apply_memory_seeds(instance, memory_seeds)

        display = StdoutConversationDisplay(show_labels=False, verbose=0)
        controller = SessionController(
            instance=instance,
            display=display,
            obs_recorder=obs_rec,
            checkpoint_store=store,
            agent_id=agent_manifest_label(config, spec_path),
            config=ConversationConfig(
                single_turn=len(queries) == 1,
                save_checkpoint_each_turn=checkpoint_save,
            ),
        )
        try:
            results = [controller.run_turn(q) for q in queries]
        finally:
            close_observability(controller)
            if obs_pipeline is not None:
                obs_pipeline.close()
            ensure_live_otel_span_files(events_path, obs_cfg)

        if checkpoint_save and store is not None:
            final_path = store.save(instance.record_checkpoint("final"), label="final")
            logger.info("Saved final checkpoint: %s", final_path)

        text = results[-1].text if results else ""

        meta: dict[str, Any] = {"run_seed": run_seed, "turns": len(queries)}
        if topology:
            meta["topology"] = topology

        return RunResult(
            content=text,
            status="ok",
            artifacts=_events_artifacts(events_path, config, spec_path),
            metadata=meta,
        )


def select_mas_runner(*, runtime_id: str | None = None) -> MasBenchRunner:
    """Return the default MAS bench runner.

    ``runtime_id`` is reserved for future multi-runtime selection; ignored today.
    """
    del runtime_id
    return MasBenchRunner()
