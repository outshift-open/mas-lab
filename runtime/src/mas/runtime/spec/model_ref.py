#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve a ``spec.models[].id`` reference or a literal LiteLLM model string.

Lives in ``runtime`` (not a higher-level library) so plugin wiring such as
``mas.runtime.contracts.cm_factory`` can resolve a ``params.model`` override
without depending on anything above the kernel.
"""

from __future__ import annotations

from typing import Any


def _spec(manifest_or_spec: dict[str, Any] | None) -> dict[str, Any]:
    raw = manifest_or_spec or {}
    if "spec" in raw or str(raw.get("kind", "")).lower() == "agent":
        spec = raw.get("spec")
        return spec if isinstance(spec, dict) else {}
    return raw if isinstance(raw, dict) else {}


def _typed_models(manifest_or_spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    models = _spec(manifest_or_spec).get("models") or []
    if not isinstance(models, list):
        return []
    return [m for m in models if isinstance(m, dict)]


def model_binding_by_id(manifest_or_spec: dict[str, Any] | None, model_id: str) -> dict[str, Any]:
    """``spec.models[]`` entry whose ``id`` matches *model_id* (default id is ``main``)."""
    wanted = str(model_id or "").strip()
    if not wanted:
        return {}
    for model in _typed_models(manifest_or_spec):
        if str(model.get("id") or "main") == wanted:
            return model
    return {}


def resolve_model_ref(
    manifest_or_spec: dict[str, Any] | None,
    ref: str | None,
    *,
    engine_model: str | None = None,
) -> tuple[str | None, str]:
    """Resolve a ``spec.models[].id`` or a LiteLLM model string.

    Default (empty *ref*) is the agent's live engine model — the same model
    used for turns. Returns ``(model_string, source)``.
    """
    token = str(ref or "").strip()
    if not token:
        return (str(engine_model).strip() or None if engine_model else None), "agent"
    entry = model_binding_by_id(manifest_or_spec, token)
    if entry:
        raw = entry.get("model")
        if isinstance(raw, str) and raw.strip():
            return raw.strip(), f"spec.models[id={token}]"
        # `token` matched a spec.models[].id, but that entry has no `model` —
        # fall back to the agent's engine model instead of sending the bare
        # id string to the provider as if it were a literal model name.
        return (str(engine_model).strip() or None if engine_model else None), "agent"
    if engine_model and token == str(engine_model).strip():
        return token, "agent"
    return token, "override"


def first_nonempty(*candidates: tuple[Any, str]) -> tuple[str | None, str]:
    """Return the first ``(value, source)`` pair whose value is a non-empty string.

    Shared by override chains that pick the first configured value out of an
    ordered list of ``(candidate, provenance-label)`` pairs.
    """
    for value, source in candidates:
        token = str(value).strip() if value else ""
        if token:
            return token, source
    return None, ""
