#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""CMFactory — thin facade over :func:`mas.runtime.registry.get_registry`.

Context managers are real strategy plugins. The summarising manager additionally
composes a **summarizer** sub-plugin (registry type ``summarizer``).

Manifest bindings are read with the lenient normalizer: ``ctl`` already
validates ``spec.context_manager``/``params.summarizer`` at authoring time,
so a malformed value reaching this per-session construction path (a manifest
built directly, bypassing ``ctl``) degrades to the platform default instead
of failing every turn.
"""

from __future__ import annotations

import inspect
from typing import Any

from mas.runtime.contracts.context_manager_contract import ContextManagerContract
from mas.runtime.registry import get_registry
from mas.runtime.spec.model_ref import resolve_model_ref
from mas.runtime.spec.plugin_binding import (
    normalize_plugin_binding_lenient,
    plugin_binding_id,
    plugin_binding_params,
)
from mas.runtime.spec.schema_bindings_generated import CONTEXT_MANAGER_ASSEMBLY_PARAM_KEYS


def _accepts_kwargs(fn: Any, *names: str) -> bool:
    """Whether callable *fn* accepts every keyword name in *names*."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return True
    declared = {p.name for p in params}
    return set(names) <= declared

# Assembly param keys come from context-manager-assembly-params.schema.yaml
# (generated). Strategy keys stay in params for ContextManagerContract ctors.
# summarizer is a sub-plugin binding, not a strategy constructor kwarg.
_NON_CTOR_PARAM_KEYS = CONTEXT_MANAGER_ASSEMBLY_PARAM_KEYS | frozenset({"summarizer"})


def _default_summarizer_id() -> str:
    return get_registry().default_for("summarizer") or "llm"


def _summarizer_model_ref(sub: dict[str, Any]) -> str | None:
    field = "spec.context_manager.params.summarizer"
    params = plugin_binding_params(sub, field=field)
    raw = params.get("model") or sub.get("model")
    token = str(raw).strip() if raw else ""
    return token or None


def _instantiate_summarizer(
    raw: Any,
    engine: Any | None,
    *,
    manifest: dict[str, Any] | None = None,
) -> Any:
    """Create a ``summarizer`` registry plugin and bind the live engine if needed."""
    field = "spec.context_manager.params.summarizer"
    sub = normalize_plugin_binding_lenient(raw, field=field)
    if not plugin_binding_id(sub, field=field):
        sub = {**sub, "type": _default_summarizer_id()}
    model_ref = _summarizer_model_ref(sub)
    plugin_id = plugin_binding_id(sub, field=field).lower()
    if model_ref and "llm" in plugin_id:
        params = dict(sub.get("params") or {})
        params.setdefault("model", model_ref)
        sub = {**sub, "params": params}
    plugin = get_registry().create("summarizer", sub)
    bind_engine = getattr(plugin, "bind_engine", None)
    if callable(bind_engine):
        engine_model = getattr(engine, "model", None)
        resolved, source = resolve_model_ref(
            manifest or getattr(engine, "manifest", None),
            model_ref,
            engine_model=str(engine_model) if engine_model else None,
        )
        bind_kwargs: dict[str, Any] = {}
        if _accepts_kwargs(bind_engine, "model"):
            bind_kwargs["model"] = resolved
        if _accepts_kwargs(bind_engine, "model_source"):
            bind_kwargs["model_source"] = source
        bind_engine(engine, **bind_kwargs)
    return plugin


def _bind_summarizer(
    instance: Any,
    binding: dict[str, Any],
    engine: Any | None,
    *,
    manifest: dict[str, Any] | None = None,
) -> None:
    bind = getattr(instance, "bind_summarizer", None)
    if not callable(bind):
        return
    params = dict(binding.get("params") or {})
    raw = params.get("summarizer")
    if raw is None:
        raw = _default_summarizer_id()
    bind(_instantiate_summarizer(raw, engine, manifest=manifest))


class CMFactory:
    """Instantiate ``spec.context_manager`` via the runtime registry.

    When the manifest omits ``spec.context_manager``, the registry default
    from ``defaults.yaml`` (overridable via workspace ``config.yaml``) is used.
    """

    @classmethod
    def create(
        cls,
        spec: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        params: dict[str, Any] | None = None,
        manifest: dict | None = None,
        engine: Any | None = None,
    ) -> ContextManagerContract:
        binding: dict[str, Any] = dict(spec or {})
        if manifest is not None and not binding:
            raw = (manifest.get("spec") or {}).get("context_manager")
            binding = normalize_plugin_binding_lenient(raw, field="spec.context_manager")
        if name:
            binding = {**binding, "type": name}
        if params:
            binding = {**binding, "params": {**(binding.get("params") or {}), **params}}
        ctor_binding = binding
        if binding.get("params"):
            ctor_binding = {
                **binding,
                "params": {
                    k: v
                    for k, v in binding["params"].items()
                    if k not in _NON_CTOR_PARAM_KEYS
                },
            }
        instance = get_registry().create("context_manager", ctor_binding, manifest=manifest)
        if not isinstance(instance, ContextManagerContract):
            raise TypeError(f"{type(instance).__name__} is not a ContextManagerContract")
        _bind_summarizer(instance, binding, engine, manifest=manifest)
        return instance

    @classmethod
    def create_from_manifest(cls, manifest: dict | None) -> ContextManagerContract:
        return cls.create(manifest=manifest)
