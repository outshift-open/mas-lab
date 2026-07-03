#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runtime instantiation — ctl applies external state; runtime receives snapshots only."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from mas.runtime.factory.builder import RuntimeBuilder
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.driver.mocks import AutoCtxAssembler

from mas.ctl.adapters.checkpoint import JsonCheckpointStore
from mas.ctl.adapters.memory_seed import (
    MemorySeed,
    MemorySeedLoader,
    apply_memory_seeds,
    seeds_from_manifest,
)
from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.session.engine_factory import build_engine
from mas.ctl.session.manifest_config import kernel_config_from_manifest
from mas.ctl.validate import validate_file, validation_enabled
from mas.ctl.workspace.config import WorkspaceConfig
from mas.runtime.agent_defaults import default_pattern_plugin_id

logger = logging.getLogger(__name__)


@dataclass
class InstantiationOptions:
    pattern_plugin_id: str = field(default_factory=default_pattern_plugin_id)
    memory_seed_path: Path | None = None
    checkpoint_path: Path | None = None
    checkpoint_dir: Path | None = None
    validate_manifests: bool = True
    agent_manifest: dict | None = None
    manifest_dir: Path | None = None
    app_root: Path | None = None
    resolved_infra: ResolvedInfra | None = None
    workspace: WorkspaceConfig | None = None
    enable_observability: bool = True
    enable_governance: bool = True
    enable_coordination: bool = True


def instantiate_runtime(
    options: InstantiationOptions,
    *,
    hitl=None,
) -> tuple[RuntimeInstance, JsonCheckpointStore | None]:
    """Ctl-owned bootstrap: validate seeds/checkpoints, build instance, restore state."""
    seeds: list[MemorySeed] = []
    if options.memory_seed_path:
        if options.validate_manifests and validation_enabled():
            validate_file(options.memory_seed_path, kind="memory_seed").raise_if_failed()
        seeds = MemorySeedLoader.load_path(options.memory_seed_path)
    if options.agent_manifest:
        seen = {s.key for s in seeds}
        for seed in seeds_from_manifest(options.agent_manifest):
            if seed.key not in seen:
                seeds.append(seed)
                seen.add(seed.key)

    store = JsonCheckpointStore(options.checkpoint_dir) if options.checkpoint_dir else None
    if store and seeds:
        store.memory_seeds = [{"key": s.key, "content": s.content} for s in seeds]

    ctx = AutoCtxAssembler(pattern_plugin_id=options.pattern_plugin_id)
    skill_base = options.app_root or options.manifest_dir
    _apply_manifest_context(
        ctx,
        options.agent_manifest,
        options.manifest_dir,
        app_root=options.app_root,
    )
    if options.agent_manifest and skill_base:
        from mas.runtime.boundary.context.skills import inject_skills_into_context

        ctx.injected_context = inject_skills_into_context(
            ctx.injected_context,
            options.agent_manifest,
            base_dir=skill_base,
        )
    ctx.capture_baseline()
    kernel_cfg = kernel_config_from_manifest(
        options.agent_manifest,
        pattern_plugin_id=options.pattern_plugin_id,
    )
    ws = options.workspace or WorkspaceConfig.load(options.manifest_dir or Path.cwd())
    selection = build_engine(
        ctx,
        options.agent_manifest,
        options.resolved_infra,
        pattern_plugin_id=options.pattern_plugin_id,
        workspace_default_model=ws.default_model,
        anchor=options.manifest_dir or Path.cwd(),
        workspace=ws,
    )
    logger.info("Engine mode=%s (%s)", selection.mode, selection.reason)

    instance = RuntimeBuilder.from_config(
        kernel_cfg,
        hitl=hitl,
        engine=selection.engine,
        ctx=ctx,
        enable_observability=options.enable_observability,
        enable_governance=options.enable_governance,
        enable_coordination=options.enable_coordination,
    )
    apply_memory_seeds(instance, seeds)
    if seeds and options.agent_manifest:
        agent_id = str((options.agent_manifest.get("metadata") or {}).get("name") or "agent")
        from mas.ctl.adapters.memory_seed import index_seeds_in_semantic_memory

        index_seeds_in_semantic_memory(seeds, agent_id=agent_id)

    if options.checkpoint_path:
        cp_store = store or JsonCheckpointStore(options.checkpoint_path.parent)
        kernel_snap = cp_store.load(options.checkpoint_path)
        instance.load_checkpoint(kernel_snap)
        if cp_store.memory_seeds:
            apply_memory_seeds(
                instance,
                [MemorySeed(key=r["key"], content=r["content"]) for r in cp_store.memory_seeds],
            )

    instance.capture_session_baseline()
    if options.agent_manifest and options.manifest_dir:
        from mas.runtime.engine.manifest_tool_provider import attach_manifest_tools_to_instance

        attach_manifest_tools_to_instance(
            instance,
            options.agent_manifest,
            options.manifest_dir,
            app_root=options.app_root or options.manifest_dir,
            workspace_root=ws.root if ws.found else None,
        )
    return instance, store


def _apply_manifest_context(
    ctx: AutoCtxAssembler,
    manifest: dict | None,
    manifest_dir: Path | None,
    *,
    app_root: Path | None = None,
) -> None:
    if not manifest:
        return
    from mas.runtime.boundary.context.chunks import resolve_context_chunk

    spec = manifest.get("spec") or {}
    base = app_root or manifest_dir or Path.cwd()
    for ref_key in ("instructions_ref", "system_prompt_ref"):
        ref = spec.get(ref_key)
        if isinstance(ref, str) and ref:
            path = (base / ref).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"{ref_key} file not found: {path}")
            ctx.injected_context.append(path.read_text(encoding="utf-8").strip())
    prompt = spec.get("system_prompt") or spec.get("instructions")
    if isinstance(prompt, str) and prompt.strip():
        ctx.injected_context.append(prompt.strip())
    context = spec.get("context") or {}
    if isinstance(context, dict):
        for key, val in context.items():
            text = resolve_context_chunk(val, base_dir=base)
            ctx.injected_context.append(f"[{key}] {text}")
