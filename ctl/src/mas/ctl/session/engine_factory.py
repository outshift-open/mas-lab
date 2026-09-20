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
from mas.ctl.infra.resolve import resolution_anchor, resolve_infra_refs
from mas.ctl.infra.resolve import api_key_for_infra
from mas.ctl.session.manifest_config import engine_use_tool_loop, kernel_config_from_manifest  # kernel_config_from_manifest: deprecated; prefer RuntimeInstance.from_spec()
from mas.ctl.workspace.config import UserConfig, WorkspaceConfig, merge_infra_refs
from mas.runtime.engine.llm_cache import resolve_cache_path
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.agent_defaults import default_pattern_plugin_id, resolve_default_model
from mas.runtime.driver.mocks import AutoCtxAssembler
from mas.runtime.kernel.config import KernelConfig

logger = logging.getLogger(__name__)

_LLM_SPEC_DEPRECATION = (
    "spec.llm is deprecated; declare model settings under spec.models[] instead"
)


def _primary_model_entry(spec: dict[str, Any]) -> dict[str, Any] | None:
    models = spec.get("models") or []
    if isinstance(models, list) and models and isinstance(models[0], dict):
        return models[0]
    return None


def _warn_llm_spec_fallback(field: str) -> None:
    logger.warning("%s (read %s from spec.llm)", _LLM_SPEC_DEPRECATION, field)


@dataclass(frozen=True)
class EngineSelection:
    engine: Any
    mode: str  # live | replay
    reason: str = ""


def _strict_replay(llm_proxy: dict[str, Any] | None) -> bool:
    """True when an llm_cache pipeline step will error on miss (offline replay)."""
    for step in (llm_proxy or {}).get("pipeline") or []:
        if not isinstance(step, dict):
            continue
        mid = str(step.get("middleware") or "")
        if mid not in {"llm_cache", "llm-cache"}:
            continue
        params = step.get("params") or {}
        if params.get("raise_on_miss") is True:
            return True
    return False


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
        entry = _primary_model_entry(spec)
        model = entry.get("model") if entry else None
        if not model:
            model = spec.get("model")
        if not model:
            llm = spec.get("llm") or {}
            if llm.get("model"):
                _warn_llm_spec_fallback("model")
                model = llm.get("model")
        if isinstance(model, str) and model.strip():
            raw = model.strip()
        elif workspace_default:
            raw = workspace_default
        else:
            raw = resolve_default_model()
        if not model and not workspace_default:
            default = llm_proxy.get("default_model")
            if default:
                raw = str(default)
    mappings = llm_proxy.get("mappings") or {}
    return str(mappings.get(raw, raw))


def _resolve_sampling_param(manifest: dict | None, key: str, default: float) -> float:
    """Read a sampling param from ``spec.models[0]``, then deprecated ``spec.llm``."""
    spec = (manifest or {}).get("spec") or {}
    entry = _primary_model_entry(spec)
    if entry and key in entry:
        return float(entry[key])
    llm = spec.get("llm") or {}
    if key in llm:
        _warn_llm_spec_fallback(key)
        return float(llm[key])
    return default


def _resolve_model_option(manifest: dict | None, key: str) -> str | None:
    """Read a string model option from ``spec.models[0]``, then deprecated ``spec.llm``."""
    spec = (manifest or {}).get("spec") or {}
    entry = _primary_model_entry(spec)
    value = entry.get(key) if entry else None
    if value is None:
        llm = spec.get("llm") or {}
        value = llm.get(key)
        if value is not None:
            _warn_llm_spec_fallback(key)
    return str(value) if value else None


def _resolve_infra_for_engine(
    manifest: dict | None,
    infra: ResolvedInfra | None,
    *,
    anchor: Path,
    workspace: WorkspaceConfig | None = None,
    runtime_refs_cli: list[str] | None = None,
) -> ResolvedInfra:
    if infra is not None and infra.llm_proxy:
        return infra
    ws = workspace or WorkspaceConfig.load(anchor)
    user = UserConfig.load()
    merged_refs = merge_infra_refs(
        workspace_refs=ws.effective_infra_refs,
        user_refs=[user.default_infra] if user.default_infra else [],
        cli_refs=[],
        workspace_found=ws.found,
    )
    if not merged_refs:
        return infra or ResolvedInfra(refs=[], llm_proxy={})
    return resolve_infra_refs(
        merged_refs,
        anchor=anchor,
        workspace=ws,
        user=user,
        runtime_refs=list(runtime_refs_cli or []),
    )


def build_engine(
    ctx: AutoCtxAssembler,
    manifest: dict | None,
    infra: ResolvedInfra | None,
    *,
    pattern_plugin_id: str | None = None,
    workspace_default_model: str | None = None,
    anchor: Path | None = None,
    workspace: WorkspaceConfig | None = None,
    kernel_config: KernelConfig | None = None,
    cache_read_override: bool | None = None,
    cache_write_override: bool | None = None,
    stream_override: bool | None = None,
    runtime_refs_cli: list[str] | None = None,
) -> EngineSelection:
    pid = pattern_plugin_id or default_pattern_plugin_id()
    kernel_cfg = kernel_config if kernel_config is not None else kernel_config_from_manifest(manifest, pattern_plugin_id=pid)
    tool_loop = engine_use_tool_loop(manifest, kernel_cfg)
    ws = workspace or WorkspaceConfig.load(anchor)
    ref_anchor = resolution_anchor(anchor, ws)

    resolved = _resolve_infra_for_engine(
        manifest,
        infra,
        anchor=ref_anchor,
        workspace=ws,
        runtime_refs_cli=runtime_refs_cli,
    )
    llm_proxy = dict(resolved.llm_proxy or {})
    strict_replay = _strict_replay(llm_proxy)

    api_base = str(llm_proxy.get("api_base") or "").strip()
    api_key_env = str(llm_proxy.get("api_key_env") or "OPENAI_API_KEY")

    api_key = api_key_for_infra(llm_proxy)
    if not api_base and not strict_replay:
        raise RuntimeError(
            "No LLM configured: resolve infra (workspace infra_refs or --infra-ref). "
            "For offline CI, attach llm_cache replay (raise_on_miss) recorded against a live provider."
        )
    if not api_key and not strict_replay:
        env_name = llm_proxy.get("api_key_env") or "OPENAI_API_KEY"
        raise RuntimeError(
            f"Live LLM configured ({api_base}) but {env_name} is unset. "
            "Set the API key, or replay from an llm_cache fixture with raise_on_miss: true."
        )
    if strict_replay:
        mode = "replay"
        reason = "llm_cache raise_on_miss"
    else:
        mode = "live"
        reason = f"resolved infra → {api_base}"

    model = resolve_model_name(manifest, resolved, workspace_default=workspace_default_model)
    cache_raw = llm_proxy.get("cache_path")
    runtime_engine = dict(resolved.runtime_engine or {})
    cache_read = _cache_read_enabled(runtime_engine, override=cache_read_override)
    cache_write = _cache_write_enabled(runtime_engine, override=cache_write_override)
    cache_active = (cache_read or cache_write) and not (llm_proxy.get("pipeline"))
    cache_path = Path(str(cache_raw)) if cache_raw else resolve_cache_path() if cache_active else None
    stream = _stream_enabled(runtime_engine, override=stream_override)

    engine = _wrap_with_infra_pipeline(
        LiveLlmEngine(
            ctx=ctx,
            manifest=manifest,
            api_base=api_base or "https://api.openai.com/v1",
            api_key_env=api_key_env,
            model=model,
            temperature=_resolve_sampling_param(manifest, "temperature", 0.7),
            max_tokens=int(_resolve_sampling_param(manifest, "max_tokens", 2000)),
            reasoning_effort=_resolve_model_option(manifest, "reasoning_effort"),
            cache_path=cache_path,
            use_cache=cache_active,
            cache_read=cache_read,
            cache_write=cache_write,
            stream=stream,
            use_tool_loop=tool_loop,
            parallel_tool_calls=kernel_cfg.parallel_tool_calls,
            llm_proxy=llm_proxy,
        ),
        llm_proxy.get("pipeline") or [],
    )
    return EngineSelection(engine=engine, mode=mode, reason=reason)


def _bool_env(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _cache_settings(runtime_engine: dict[str, Any]) -> dict[str, Any]:
    cache = (runtime_engine or {}).get("cache") or {}
    return cache if isinstance(cache, dict) else {}


def _cache_read_enabled(
    runtime_engine: dict[str, Any],
    *,
    override: bool | None = None,
) -> bool:
    if override is not None:
        return override
    cache = _cache_settings(runtime_engine)
    if cache.get("enabled") is False:
        return False
    if isinstance(cache.get("read"), bool):
        return cache["read"]
    env = _bool_env("MAS_LLM_CACHE_READ")
    if env is not None:
        return env
    return True


def _cache_write_enabled(
    runtime_engine: dict[str, Any],
    *,
    override: bool | None = None,
) -> bool:
    if override is not None:
        return override
    cache = _cache_settings(runtime_engine)
    if cache.get("enabled") is False:
        return False
    if isinstance(cache.get("write"), bool):
        return cache["write"]
    env = _bool_env("MAS_LLM_CACHE_WRITE")
    if env is not None:
        return env
    return True


def _stream_enabled(
    runtime_engine: dict[str, Any],
    *,
    override: bool | None = None,
) -> bool:
    if override is not None:
        return override
    if isinstance((runtime_engine or {}).get("stream"), bool):
        return bool(runtime_engine["stream"])
    env = _bool_env("MAS_LLM_STREAM")
    if env is not None:
        return env
    return False


def _wrap_with_infra_pipeline(engine: Any, pipeline: list[dict[str, Any]]) -> Any:
    if not pipeline:
        return engine
    from mas.runtime.engine.infra_pipeline import wrap_bidirectional_pipeline

    return wrap_bidirectional_pipeline(engine, list(pipeline))
