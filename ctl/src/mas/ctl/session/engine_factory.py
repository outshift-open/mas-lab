#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Select EngineContract implementation from manifest + resolved infra."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.infra.resolve import resolve_infra_refs
from mas.ctl.infra.resolve import InfraResolveError
from mas.ctl.infra.resolve import api_key_for_infra
from mas.ctl.session.manifest_config import engine_use_tool_loop, kernel_config_from_manifest
from mas.ctl.workspace.config import UserConfig, WorkspaceConfig, collect_mas_infra_refs, merge_infra_refs
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.agent_defaults import CANONICAL_DEFAULT_MODEL, default_pattern_plugin_id
from mas.runtime.driver.mocks import AutoCtxAssembler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineSelection:
    engine: Any
    mode: str  # live | mock
    reason: str = ""


def is_mock_mode(manifest: dict | None, infra: ResolvedInfra | None) -> bool:
    spec = (manifest or {}).get("spec") or {}
    execution = spec.get("execution") or {}
    mocking = execution.get("mocking") or {}
    if mocking.get("enabled") is True:
        return True
    llm = spec.get("llm") or {}
    if str(llm.get("provider", "")).lower() == "mock":
        return True
    if os.environ.get("MAS_MOCK_LLM", "").lower() in ("1", "true", "yes"):
        return True
    llm_proxy = (infra.llm_proxy if infra else {}) or {}
    if llm_proxy.get("mock"):
        return True
    refs = infra.refs if infra else []
    return any("mock-llm" in r for r in refs)


def resolve_model_name(
    manifest: dict | None,
    infra: ResolvedInfra | None,
    *,
    workspace_default: str | None = None,
) -> str:
    llm_proxy = (infra.llm_proxy if infra else {}) or {}
    forced = (
        os.environ.get("MAS_CTL_MODEL", "").strip()
        or os.environ.get("MAS_LLM_MODEL", "").strip()
    )
    if forced:
        raw = forced
    else:
        spec = (manifest or {}).get("spec") or {}
        llm = spec.get("llm") or {}
        models = spec.get("models") or []
        model = llm.get("model") or spec.get("model")
        if not model and isinstance(models, list) and models:
            first = models[0]
            if isinstance(first, dict):
                model = first.get("model")
        if isinstance(model, str) and model.strip():
            raw = model.strip()
        elif workspace_default:
            raw = workspace_default
        else:
            raw = CANONICAL_DEFAULT_MODEL
        if not model and not workspace_default:
            default = llm_proxy.get("default_model")
            if default:
                raw = str(default)
    mappings = llm_proxy.get("mappings") or {}
    return str(mappings.get(raw, raw))


def _resolve_infra_for_engine(
    manifest: dict | None,
    infra: ResolvedInfra | None,
    *,
    anchor: Path,
    workspace: WorkspaceConfig | None = None,
) -> ResolvedInfra:
    if infra is not None and infra.llm_proxy:
        return infra
    ws = workspace or WorkspaceConfig.load(anchor)
    user = UserConfig.load()
    merged_refs = merge_infra_refs(
        mas_refs=collect_mas_infra_refs((manifest or {}).get("spec") or manifest or {}),
        workspace_refs=ws.effective_infra_refs,
        user_refs=[user.default_infra] if user.default_infra else [],
        cli_refs=[],
        workspace_found=ws.found,
    )
    if not merged_refs and is_mock_mode(manifest, infra):
        merged_refs = ["standard:mock-llm"]
    if not merged_refs:
        return infra or ResolvedInfra(refs=[], llm_proxy={})
    try:
        return resolve_infra_refs(merged_refs, anchor=anchor, workspace=ws, user=user)
    except InfraResolveError:
        if is_mock_mode(manifest, infra):
            return resolve_infra_refs(["standard:mock-llm"], anchor=anchor, workspace=ws, user=user)
        raise


def build_engine(
    ctx: AutoCtxAssembler,
    manifest: dict | None,
    infra: ResolvedInfra | None,
    *,
    pattern_plugin_id: str | None = None,
    workspace_default_model: str | None = None,
    anchor: Path | None = None,
    workspace: WorkspaceConfig | None = None,
) -> EngineSelection:
    pid = pattern_plugin_id or default_pattern_plugin_id()
    kernel_cfg = kernel_config_from_manifest(manifest, pattern_plugin_id=pid)
    tool_loop = engine_use_tool_loop(manifest, kernel_cfg)
    ref_anchor = anchor or Path.cwd()

    resolved = _resolve_infra_for_engine(
        manifest, infra, anchor=ref_anchor, workspace=workspace
    )
    llm_proxy = dict(resolved.llm_proxy or {})
    mock = is_mock_mode(manifest, resolved) or bool(llm_proxy.get("mock"))

    llm_spec = ((manifest or {}).get("spec") or {}).get("llm") or {}
    api_base = str(llm_proxy.get("api_base") or "").strip()
    api_key_env = str(llm_proxy.get("api_key_env") or "OPENAI_API_KEY")

    if mock:
        mode = "mock"
        reason = "execution.mocking, mock infra ref, or model_access provider"
    else:
        api_key = api_key_for_infra(llm_proxy)
        if not api_base:
            raise RuntimeError(
                "No LLM configured: resolve infra (workspace infra_refs or --infra-ref), "
                "or enable spec.execution.mocking / a mock infra ref."
            )
        if not api_key:
            env_name = llm_proxy.get("api_key_env") or "OPENAI_API_KEY"
            raise RuntimeError(
                f"Live LLM configured ({api_base}) but {env_name} is unset. "
                "Set the API key or enable spec.execution.mocking."
            )
        mode = "live"
        reason = f"resolved infra → {api_base}"

    model = resolve_model_name(manifest, resolved, workspace_default=workspace_default_model)
    cache_raw = llm_proxy.get("cache_path")
    cache_path = Path(str(cache_raw)) if cache_raw else None

    engine = _wrap_with_infra_pipeline(
        LiveLlmEngine(
            ctx=ctx,
            manifest=manifest,
            api_base=api_base or "mock://local",
            api_key_env=api_key_env,
            model=model,
            temperature=float(llm_spec.get("temperature", 0.7)),
            max_tokens=int(llm_spec.get("max_tokens", 2000)),
            cache_path=cache_path,
            use_cache=_use_cache(manifest) and not mock and not (llm_proxy.get("pipeline")),
            use_tool_loop=tool_loop,
            parallel_tool_calls=kernel_cfg.parallel_tool_calls,
            llm_proxy=llm_proxy,
        ),
        llm_proxy.get("pipeline") or [],
    )
    if mock:
        from mas.runtime.engine.leaf import leaf_engine

        leaf = leaf_engine(engine)
        if getattr(leaf, "_model_access", None) is None:
            ma_cfg = llm_proxy.get("model_access")
            if isinstance(ma_cfg, dict) and ma_cfg:
                raise RuntimeError(
                    "Mock mode has model_access infra config but no plugin was loaded. "
                    "Check module_path/class_name, or see ModelAccessLoadError above "
                    "if instantiation failed."
                )
            raise RuntimeError(
                "Mock mode requires model_access from standard:mock-llm infra "
                "(enable spec.execution.mocking or pass a mock infra ref)."
            )
    return EngineSelection(engine=engine, mode=mode, reason=reason)


def _use_cache(manifest: dict | None) -> bool:
    spec = (manifest or {}).get("spec") or {}
    execution = spec.get("execution") or {}
    cache = execution.get("cache") or {}
    if cache.get("enabled") is False:
        return False
    return True


def _wrap_with_infra_pipeline(engine: Any, pipeline: list[dict[str, Any]]) -> Any:
    if not pipeline:
        return engine
    from mas.runtime.engine.infra_pipeline import wrap_bidirectional_pipeline

    return wrap_bidirectional_pipeline(engine, list(pipeline))
