#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runtime instantiation — ctl applies external state; runtime receives snapshots only."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
from mas.ctl.validate import validate_file, validation_enabled
from mas.ctl.workspace.config import WorkspaceConfig
from mas.runtime.agent_defaults import default_pattern_plugin_id
from mas.runtime.boundary.context.manifest_context import context_chunks_from_spec

logger = logging.getLogger(__name__)

_SKILL_TOOL_REFS = {
    "skills:tools/skill-access.tool.yaml",
    "pkg://skills/tools/skill-access.tool.yaml",
}
_SKILL_SHELL_REFS = {
    "skills:tools/run-skill-script.tool.yaml",
    "pkg://skills/tools/run-skill-script.tool.yaml",
}
_SUPPORTED_SKILL_IMPLS = {"native", "adk", "langchain"}


@dataclass(frozen=True)
class _SkillPluginConfig:
    impl: str = "native"
    base_dir: Path | None = None
    auto_inject_scripts: bool = False


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
    # Resolve skills relative to the agent manifest directory first.
    # app_root can be '.' for some compose flows and would break relative refs.
    skill_base = options.manifest_dir or options.app_root
    skill_cfg = _resolve_skill_plugin_config(
        options.agent_manifest,
        default_base_dir=skill_base or Path.cwd(),
    )
    _auto_inject_skill_tools(options.agent_manifest, auto_inject_scripts=skill_cfg.auto_inject_scripts)
    _apply_manifest_context(
        ctx,
        options.agent_manifest,
        options.manifest_dir,
        app_root=options.app_root,
    )
    if options.agent_manifest and skill_base:
        from mas.library.skills.plugins.sk_catalog import attach_skill_catalog_plugin

        attach_skill_catalog_plugin(
            ctx,
            options.agent_manifest,
            skill_cfg.base_dir or skill_base,
            impl=skill_cfg.impl,
        )
    ctx.capture_baseline()
    spec = dict((options.agent_manifest or {}).get("spec") or {})
    # Keep agent spec isolated from MAS workflow policy. We only surface agency
    # participants (read-only) when available for context/routing helpers.
    if "agency" not in spec:
        mas_cfg = None
        composed_app = getattr(getattr(options, "bind", None), "composed_application", None)
        if composed_app is not None:
            mas_cfg = getattr(composed_app, "config", None)
        # Fallback source when available through agent_manifest wrappers.
        if mas_cfg is None and options.agent_manifest and isinstance(options.agent_manifest.get("mas"), dict):
            mas_cfg = options.agent_manifest.get("mas")

        if isinstance(mas_cfg, dict):
            mas_spec = mas_cfg.get("spec") if isinstance(mas_cfg.get("spec"), dict) else mas_cfg
            agency = mas_spec.get("agency") if isinstance(mas_spec, dict) else None
            if isinstance(agency, dict) and agency.get("agents"):
                spec["agency"] = {"agents": list(agency.get("agents") or [])}
    ws = options.workspace or WorkspaceConfig.load(options.manifest_dir or Path.cwd())
    # Pre-parse spec to derive kernel config once; pass to build_engine to avoid double-parsing.
    from mas.runtime.spec.parser import parse_agent_spec

    _kernel_cfg, _obs_binding = parse_agent_spec(spec)
    selection = build_engine(
        ctx,
        options.agent_manifest,
        options.resolved_infra,
        pattern_plugin_id=options.pattern_plugin_id,
        workspace_default_model=ws.default_model,
        anchor=options.manifest_dir or Path.cwd(),
        workspace=ws,
        kernel_config=_kernel_cfg,
    )
    logger.info("Engine mode=%s (%s)", selection.mode, selection.reason)

    from mas.runtime.boundary.context.working_memory_compaction import (
        apply_working_memory_compaction,
    )

    apply_working_memory_compaction(spec, engine=selection.engine)
    if "context_manager" in spec and options.agent_manifest is not None:
        # LiveLlmEngine holds a live reference to options.agent_manifest (not
        # `spec` above, a separate shallow copy) and reads context_manager
        # fresh from it on every assemble_llm_messages() call -- keep both in
        # sync so the facade takes effect for the engine actually constructed
        # above, not just the copy this function goes on to use locally.
        options.agent_manifest.setdefault("spec", {})["context_manager"] = spec["context_manager"]

    instance = RuntimeInstance.from_spec(
        spec,
        base_dir=options.manifest_dir,
        agent_id=str(options.manifest_dir or "agent"),
        hitl=hitl,
        engine=selection.engine,
        ctx=ctx,
        enable_observability=options.enable_observability,
        enable_governance=options.enable_governance,
        enable_coordination=options.enable_coordination,
    )
    working_memory_spec = spec.get("working_memory")
    if isinstance(working_memory_spec, dict):
        from mas.runtime.boundary.context.working_memory_registry import WorkingMemoryConfig

        instance.working_memory = WorkingMemoryConfig(
            persistent=bool(working_memory_spec.get("persistent", True))
        )
    apply_memory_seeds(instance, seeds)
    if seeds and options.agent_manifest:
        from mas.ctl.executor.mas_session import agent_manifest_label

        agent_id = agent_manifest_label(
            options.agent_manifest,
            options.manifest_dir or Path.cwd(),
        )
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
    # Attach tools even in CLI-only mode (manifest_dir may be None for --tool flags)
    if options.agent_manifest:
        from mas.runtime.engine.manifest_tool_provider import attach_manifest_tools_to_instance

        attach_manifest_tools_to_instance(
            instance,
            options.agent_manifest,
            options.manifest_dir or Path.cwd(),
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
    spec = manifest.get("spec") or {}
    base = app_root or manifest_dir or Path.cwd()
    ctx.injected_context.extend(context_chunks_from_spec(spec, base_dir=base))


def _resolve_skill_plugin_config(
    manifest: dict[str, Any] | None,
    *,
    default_base_dir: Path,
) -> _SkillPluginConfig:
    """Resolve skill plugin implementation from overlay/manifest/env settings.

    Priority: spec.context_sources (plugin list, same shape as observability)
    > legacy manifest tool/context declarations > env var > default.
    """
    env_impl = str(os.getenv("MAS_SKILL_IMPL") or "").strip().lower() or "native"
    impl = env_impl if env_impl in _SUPPORTED_SKILL_IMPLS else "native"
    rel_base: str | None = None
    auto_inject_scripts = False

    spec = manifest.get("spec") if isinstance(manifest, dict) and isinstance(manifest.get("spec"), dict) else {}
    context_sources_raw = spec.get("context_sources") if isinstance(spec, dict) else None
    if context_sources_raw:
        from mas.runtime.spec.context_sources import parse_context_sources

        plugins, configs = parse_context_sources(context_sources_raw)
        for candidate_impl in plugins:
            if candidate_impl in _SUPPORTED_SKILL_IMPLS:
                impl = candidate_impl
            else:
                logger.warning(
                    "Unknown context_sources plugin %r; expected one of %s",
                    candidate_impl,
                    sorted(_SUPPORTED_SKILL_IMPLS),
                )
        for cfg in configs.values():
            candidate_base = cfg.get("base_dir")
            if isinstance(candidate_base, str) and candidate_base.strip():
                rel_base = candidate_base
            if "auto_inject" in cfg:
                auto_inject_scripts = bool(cfg.get("auto_inject"))

    for entry in _iter_skill_plugin_entries(manifest):
        candidate_impl = _entry_skill_impl(entry)
        if candidate_impl:
            normalized = candidate_impl.strip().lower()
            if normalized in _SUPPORTED_SKILL_IMPLS:
                impl = normalized
            else:
                logger.warning(
                    "Unknown skill impl %r; expected one of %s",
                    candidate_impl,
                    sorted(_SUPPORTED_SKILL_IMPLS),
                )
        candidate_base = _entry_skill_base_dir(entry)
        if candidate_base:
            rel_base = candidate_base

    resolved_base = default_base_dir
    if rel_base:
        p = Path(rel_base)
        resolved_base = p.resolve() if p.is_absolute() else (default_base_dir / p).resolve()

    return _SkillPluginConfig(impl=impl, base_dir=resolved_base, auto_inject_scripts=auto_inject_scripts)


def _iter_skill_plugin_entries(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not manifest:
        return []

    entries: list[dict[str, Any]] = []
    spec = manifest.get("spec") if isinstance(manifest.get("spec"), dict) else {}

    for tools_block in (spec.get("tools"), manifest.get("tools")):
        if not isinstance(tools_block, list):
            continue
        for item in tools_block:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("ref") or "").strip()
            if ref in _SKILL_TOOL_REFS or ref in _SKILL_SHELL_REFS:
                entries.append(item)

    return entries


def _entry_skill_impl(entry: dict[str, Any]) -> str | None:
    impl = entry.get("impl")
    if isinstance(impl, str) and impl.strip():
        return impl
    params = entry.get("params")
    if isinstance(params, dict):
        p_impl = params.get("impl")
        if isinstance(p_impl, str) and p_impl.strip():
            return p_impl
    return None


def _entry_skill_base_dir(entry: dict[str, Any]) -> str | None:
    for key in ("base-dir", "base_dir"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value
    params = entry.get("params")
    if isinstance(params, dict):
        value = params.get("base_dir")
        if isinstance(value, str) and value.strip():
            return value
    return None


def _auto_inject_skill_tools(manifest: dict[str, Any] | None, *, auto_inject_scripts: bool = False) -> None:
    """Auto-add skill tool refs when ``spec.skills`` is set.

    SkillCatalogPlugin/SkillToolsPlugin should not require the user to
    hand-declare ``skill-access.tool.yaml`` — presence of ``spec.skills: [...]``
    is enough to enable model-driven skill activation. That one is always
    auto-injected: it is read-only (activate_skill/list_skill_files/
    read_skill_file).

    ``run-skill-script.tool.yaml`` (shell/script execution) is a trust
    decision, not a manifest-authoring convenience — see
    library-skills/docs/user-guide.md's "Shell tool" section. It is only
    auto-injected when the deployment has opted in via
    ``spec.context_sources: [{native: {auto_inject: true}}]`` (see
    _resolve_skill_plugin_config), never merely because ``spec.skills`` is
    non-empty. Default is off: declaring skills must not silently grant
    script execution.
    """
    if not manifest:
        return
    spec = manifest.get("spec")
    if not isinstance(spec, dict):
        return
    skills = spec.get("skills")
    if not isinstance(skills, list) or not skills:
        return

    tools = spec.get("tools")
    if not isinstance(tools, list):
        tools = []

    existing_refs = {
        str(item.get("ref") or "").strip()
        for item in tools
        if isinstance(item, dict)
    }

    def _add_if_missing(ref: str) -> None:
        if ref not in existing_refs and f"pkg://{ref.split(':', 1)[1]}" not in existing_refs:
            tools.append({"ref": ref})
            existing_refs.add(ref)

    _add_if_missing("skills:tools/skill-access.tool.yaml")
    if auto_inject_scripts:
        _add_if_missing("skills:tools/run-skill-script.tool.yaml")

    spec["tools"] = tools
