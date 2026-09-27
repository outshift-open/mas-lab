#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve a ``spec.models[].id`` reference or a literal LiteLLM model string.

Lives in ``runtime`` (not a higher-level library) so plugin wiring such as
``mas.runtime.contracts.cm_factory`` can resolve a ``params.model`` override
without depending on anything above the kernel.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ANY_MODEL = "any"
SLOT_MAIN = "main"
SLOT_SUMMARIZER = "summarizer"
SLOT_JUDGE = "judge"


def is_any(value: Any) -> bool:
    """True when *value* is omitted, blank, or the ``any`` sentinel."""
    token = str(value).strip().lower() if value else ""
    return token in ("", ANY_MODEL)


def concrete_model(value: Any) -> str | None:
    """Return a LiteLLM id, or ``None`` when the spec says ``any`` / omitted."""
    if value is None:
        return None
    token = str(value).strip()
    if not token or token.lower() == ANY_MODEL:
        return None
    return token


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


def primary_model_binding(manifest_or_spec: dict[str, Any] | None) -> dict[str, Any]:
    """First ``spec.models[]`` entry, preferring ``id: main``.

    Models live on Agent and MAS ``spec.models[]``. An empty return means
    this document omitted ``spec.models``.
    """
    typed = _typed_models(manifest_or_spec)
    for model in typed:
        if str(model.get("id") or "main") == "main":
            return model
    return typed[0] if typed else {}


def primary_model_string(manifest_or_spec: dict[str, Any] | None) -> str | None:
    """Concrete LiteLLM string of the primary ``spec.models[]`` entry.

    ``any`` / omitted is not a provider id — callers inherit the next layer
    (MAS, experiment, then local ``config.yaml``).
    """
    return concrete_model(primary_model_binding(manifest_or_spec).get("model"))


def resolve_model_ref(
    manifest_or_spec: dict[str, Any] | None,
    ref: str | None,
    *,
    engine_model: str | None = None,
) -> tuple[str | None, str]:
    """Resolve a ``spec.models[].id`` or a LiteLLM model string.

    Default (empty *ref* or ``any``) is **this agent's** live engine
    (already resolved Agent → MAS → experiment → local config).
    Returns ``(model_string, source)``.
    """
    token = str(ref or "").strip()
    if not token or is_any(token):
        return (str(engine_model).strip() or None if engine_model else None), "agent"
    entry = model_binding_by_id(manifest_or_spec, token)
    if entry:
        raw = concrete_model(entry.get("model"))
        if raw:
            return raw, f"spec.models[id={token}]"
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


def first_concrete(*candidates: tuple[Any, str]) -> tuple[str | None, str]:
    """Like :func:`first_nonempty` but skips the ``any`` sentinel."""
    for value, source in candidates:
        token = concrete_model(value)
        if token:
            return token, source
    return None, ""


def normalize_model_slots(
    *,
    model: Any = None,
    models: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Concrete experiment/lab slot map.

    ``experiment.models`` keys match Agent/MAS ``spec.models[].id`` plus
    ``judge``. Scalar ``experiment.model`` is shorthand for ``models.main``;
    ``models.main`` wins when both are set. ``any`` / blank values are dropped.
    """
    out: dict[str, str] = {}
    if isinstance(models, Mapping):
        for key, value in models.items():
            slot = str(key).strip()
            token = concrete_model(value)
            if slot and token:
                out[slot] = token
    main = out.get(SLOT_MAIN) or concrete_model(model)
    if main:
        out[SLOT_MAIN] = main
    return out


def slot_model(slots: Mapping[str, Any] | None, slot: str) -> str | None:
    """Concrete LiteLLM id for *slot*, or ``None`` when unbound."""
    if not slots:
        return None
    return concrete_model(slots.get(slot))


def resolve_slot(
    slot: str,
    *,
    agent_spec: dict[str, Any] | None = None,
    parent_spec: dict[str, Any] | None = None,
    model_slots: Mapping[str, Any] | None = None,
    engine_model: str | None = None,
) -> tuple[str | None, str]:
    """Resolve one named slot: Agent → MAS → experiment.models[slot] → engine.

    Empty *slot* defaults to ``main``. The engine fallback is the already
    resolved turn model (``source=agent``).
    """
    wanted = str(slot or SLOT_MAIN).strip() or SLOT_MAIN
    agent_val = concrete_model(model_binding_by_id(agent_spec, wanted).get("model"))
    parent_val = concrete_model(model_binding_by_id(parent_spec, wanted).get("model"))
    exp_val = slot_model(model_slots, wanted)
    exp_source = "experiment.model" if wanted == SLOT_MAIN else f"experiment.models.{wanted}"
    return first_concrete(
        (agent_val, "spec.models" if wanted == SLOT_MAIN else f"spec.models[id={wanted}]"),
        (parent_val, "mas.spec.models" if wanted == SLOT_MAIN else f"mas.spec.models[id={wanted}]"),
        (exp_val, exp_source),
        (engine_model, "agent"),
    )
