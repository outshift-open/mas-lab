#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""History token budget from the model context window.

Used by the assembler plugin (``manage_history`` hint + payload trim) and by
``mas-ctl compile`` (fill omitted context-manager params). Not imported by
runtime: the kernel does not choose a history budget.

History max size = model ``context_window`` minus reserved completion space
(``models[].max_tokens``) and any explicit ``trimmer.reserve_tokens``.
"""

from __future__ import annotations

from typing import Any

from mas.runtime.spec.defaults import (
    DEFAULT_CONTEXT_RESERVE_TOKENS,
    DEFAULT_HYSTERESIS_RATIO,
    DEFAULT_KEEP_TURNS,
    DEFAULT_MODEL_CONTEXT_WINDOW,
    DEFAULT_MODEL_MAX_TOKENS,
    DEFAULT_WORKING_MEMORY_MESSAGES,
)


def _spec(manifest_or_spec: dict[str, Any] | None) -> dict[str, Any]:
    raw = manifest_or_spec or {}
    if "spec" in raw or str(raw.get("kind", "")).lower() == "agent":
        spec = raw.get("spec")
        return spec if isinstance(spec, dict) else {}
    return raw if isinstance(raw, dict) else {}


def primary_model_binding(manifest_or_spec: dict[str, Any] | None) -> dict[str, Any]:
    """First ``spec.models[]`` entry, preferring ``id: main``."""
    models = _spec(manifest_or_spec).get("models") or []
    if not isinstance(models, list):
        return {}
    typed = [m for m in models if isinstance(m, dict)]
    for model in typed:
        if str(model.get("id") or "main") == "main":
            return model
    return typed[0] if typed else {}


def model_context_window(manifest_or_spec: dict[str, Any] | None) -> int:
    raw = primary_model_binding(manifest_or_spec).get("context_window")
    if raw is None:
        return DEFAULT_MODEL_CONTEXT_WINDOW
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MODEL_CONTEXT_WINDOW
    return value if value >= 1 else DEFAULT_MODEL_CONTEXT_WINDOW


def model_completion_tokens(manifest_or_spec: dict[str, Any] | None) -> int:
    """Tokens reserved for the model completion (``models[].max_tokens``)."""
    raw = primary_model_binding(manifest_or_spec).get("max_tokens")
    if raw is None:
        return DEFAULT_MODEL_MAX_TOKENS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MODEL_MAX_TOKENS
    return value if value >= 1 else DEFAULT_MODEL_MAX_TOKENS


def explicit_trimmer(manifest_or_spec: dict[str, Any] | None) -> dict[str, Any]:
    cm = _spec(manifest_or_spec).get("context_manager") or {}
    params = cm.get("params") if isinstance(cm, dict) else {}
    trimmer = params.get("trimmer") if isinstance(params, dict) else None
    return trimmer if isinstance(trimmer, dict) else {}


def derived_trimmer_params(manifest_or_spec: dict[str, Any] | None) -> tuple[int, int]:
    """Return ``(max_tokens, reserve_tokens)`` for assembly trim.

    Explicit ``params.trimmer`` wins; otherwise max_tokens is the model
    context window and reserve is the completion budget.
    """
    trimmer = explicit_trimmer(manifest_or_spec)
    raw_max = trimmer.get("max_tokens", trimmer.get("token_budget"))
    context_window = model_context_window(manifest_or_spec)
    completion = model_completion_tokens(manifest_or_spec)
    if raw_max is not None:
        try:
            max_tokens = int(raw_max)
        except (TypeError, ValueError):
            max_tokens = context_window
        if max_tokens < 1:
            max_tokens = context_window
    else:
        max_tokens = context_window
    raw_reserve = trimmer.get("reserve_tokens")
    if raw_reserve is not None:
        try:
            reserve = int(raw_reserve)
        except (TypeError, ValueError):
            reserve = completion
        reserve = max(0, reserve)
    else:
        reserve = completion if completion >= 1 else DEFAULT_CONTEXT_RESERVE_TOKENS
    return max_tokens, reserve


def history_token_budget(manifest_or_spec: dict[str, Any] | None) -> int:
    """Tokens available for committed history (window minus completion reserve)."""
    max_tokens, reserve = derived_trimmer_params(manifest_or_spec)
    return max(1, max_tokens - reserve)


def assembly_trimmer_params(manifest: dict | None) -> tuple[int, int] | None:
    """Return ``(max_tokens, reserve_tokens)`` for the assembled payload cap.

    Uses explicit ``spec.context_manager.params.trimmer`` when set; otherwise
    the primary model's ``context_window`` minus completion ``max_tokens``.
    """
    max_tokens, reserve = derived_trimmer_params(manifest)
    if max_tokens < 1:
        return None
    return max_tokens, max(0, reserve)


def context_manager_history_budget_hint(manifest: dict | None) -> int:
    """Token hint for ``manage_history``: context window minus completion reserve."""
    return history_token_budget(manifest)


def _normalise_cm_type(cm: dict[str, Any]) -> str:
    raw = str(cm.get("type") or cm.get("ref") or "").strip().lower()
    return raw.replace("_", "-")


def _is_summarising_type(cm_type: str) -> bool:
    return "summaris" in cm_type


def _is_sliding_type(cm_type: str) -> bool:
    return "sliding" in cm_type


def fill_model_window_defaults(spec: dict[str, Any]) -> None:
    """Write ``context_window`` on model entries that omit it (compile visibility)."""
    models = spec.get("models")
    if not isinstance(models, list):
        return
    for model in models:
        if isinstance(model, dict) and model.get("context_window") is None:
            model["context_window"] = DEFAULT_MODEL_CONTEXT_WINDOW


def fill_context_manager_defaults(spec: dict[str, Any]) -> None:
    """Fill omitted ``spec.context_manager`` type and recency/trimmer params.

    ``mas-ctl compile`` calls this so the resolved agent YAML shows the history
    policy. The assembler plugin derives the same numbers when the keys are absent.
    """
    from mas.runtime.agent_defaults import default_context_manager_id
    from mas.runtime.spec.plugin_binding import normalize_plugin_binding

    fill_model_window_defaults(spec)

    cm = normalize_plugin_binding(spec.get("context_manager"), field="spec.context_manager")
    spec["context_manager"] = cm
    if not (cm.get("type") or cm.get("ref")):
        cm["type"] = default_context_manager_id()

    params = cm.get("params")
    if not isinstance(params, dict):
        params = {}
        cm["params"] = params

    cm_type = _normalise_cm_type(cm)
    keep = DEFAULT_KEEP_TURNS
    for key in ("keep_turns", "window_size", "max_turns"):
        raw = params.get(key)
        if raw is not None:
            try:
                keep = max(1, int(raw))
                break
            except (TypeError, ValueError):
                continue

    if _is_summarising_type(cm_type):
        from mas.runtime.registry import get_registry

        params.setdefault("keep_turns", keep)
        params.setdefault("hysteresis_ratio", DEFAULT_HYSTERESIS_RATIO)
        params.setdefault("summary_threshold", history_token_budget({"spec": spec}))
        params.setdefault("summarizer", get_registry().default_for("summarizer") or "llm")
    elif _is_sliding_type(cm_type) or not cm_type:
        params.setdefault("keep_turns", keep)
        params.setdefault("window_size", keep)

    params.setdefault("working_memory_messages", DEFAULT_WORKING_MEMORY_MESSAGES)

    trimmer = params.get("trimmer")
    if not isinstance(trimmer, dict):
        trimmer = {}
        params["trimmer"] = trimmer
    max_tokens, reserve = derived_trimmer_params({"spec": spec})
    if trimmer.get("max_tokens") is None and trimmer.get("token_budget") is None:
        trimmer["max_tokens"] = max_tokens
    trimmer.setdefault("reserve_tokens", reserve)
