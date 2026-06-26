#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Select EngineContract implementation from manifest + resolved infra."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.infra.resolve import api_key_for_infra
from mas.ctl.session.manifest_config import engine_use_tool_loop, kernel_config_from_manifest
from mas.runtime.engine.conversation import ConversationEngine
from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.agent_defaults import CANONICAL_DEFAULT_MODEL, default_pattern_plugin_id

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
    return any("mock" in r.lower() for r in refs)


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


def build_engine(
    ctx: AutoCtxAssembler,
    manifest: dict | None,
    infra: ResolvedInfra | None,
    *,
    pattern_plugin_id: str | None = None,
    workspace_default_model: str | None = None,
) -> EngineSelection:
    pid = pattern_plugin_id or default_pattern_plugin_id()
    kernel_cfg = kernel_config_from_manifest(manifest, pattern_plugin_id=pid)
    tool_loop = engine_use_tool_loop(manifest, kernel_cfg)

    if is_mock_mode(manifest, infra):
        return EngineSelection(
            engine=ConversationEngine(ctx=ctx, use_tool_loop=tool_loop),
            mode="mock",
            reason="execution.mocking or mock infra ref",
        )

    llm_proxy = (infra.llm_proxy if infra else {}) or {}
    api_base = str(llm_proxy.get("api_base") or "").strip()
    api_key = api_key_for_infra(llm_proxy)

    if api_base and api_key:
        model = resolve_model_name(manifest, infra, workspace_default=workspace_default_model)
        llm_spec = ((manifest or {}).get("spec") or {}).get("llm") or {}
        return EngineSelection(
            engine=_wrap_with_infra_pipeline(
                LiveLlmEngine(
                    ctx=ctx,
                    manifest=manifest,
                    api_base=api_base,
                    api_key_env=str(llm_proxy.get("api_key_env") or "OPENAI_API_KEY"),
                    model=model,
                    temperature=float(llm_spec.get("temperature", 0.7)),
                    max_tokens=int(llm_spec.get("max_tokens", 2000)),
                    cache_path=_cache_path(llm_proxy),
                    use_cache=_use_cache(manifest) and not (llm_proxy.get("pipeline")),
                    use_tool_loop=tool_loop,
                    parallel_tool_calls=kernel_cfg.parallel_tool_calls,
                    llm_proxy=dict(llm_proxy),
                ),
                llm_proxy.get("pipeline") or [],
            ),
            mode="live",
            reason=f"resolved infra → {api_base}",
        )

    if api_base and not api_key:
        env_name = llm_proxy.get("api_key_env") or "OPENAI_API_KEY"
        raise RuntimeError(
            f"Live LLM configured ({api_base}) but {env_name} is unset. "
            "Set the API key or enable spec.execution.mocking."
        )

    raise RuntimeError(
        "No LLM configured: resolve infra (workspace infra_refs or --infra-ref), "
        "or enable spec.execution.mocking / a mock infra ref."
    )


def _use_cache(manifest: dict | None) -> bool:
    spec = (manifest or {}).get("spec") or {}
    execution = spec.get("execution") or {}
    cache = execution.get("cache") or {}
    if cache.get("enabled") is False:
        return False
    return True


def _cache_path(llm_proxy: dict[str, Any]) -> Any:
    from pathlib import Path

    raw = llm_proxy.get("cache_path")
    if raw:
        return Path(str(raw))
    return None


def _wrap_with_infra_pipeline(engine: Any, pipeline: list[dict[str, Any]]) -> Any:
    if not pipeline:
        return engine
    from mas.runtime.engine.infra_pipeline import wrap_bidirectional_pipeline

    return wrap_bidirectional_pipeline(engine, list(pipeline))
