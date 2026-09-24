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

from typing import Any

from mas.runtime.contracts.context_manager_contract import ContextManagerContract
from mas.runtime.registry import get_registry
from mas.runtime.spec.plugin_binding import normalize_plugin_binding_lenient, plugin_binding_id
from mas.runtime.spec.schema_bindings_generated import CONTEXT_MANAGER_ASSEMBLY_PARAM_KEYS

# Assembly param keys come from context-manager-assembly-params.schema.yaml
# (generated). Strategy keys stay in params for ContextManagerContract ctors.
# summarizer is a sub-plugin binding, not a strategy constructor kwarg.
_NON_CTOR_PARAM_KEYS = CONTEXT_MANAGER_ASSEMBLY_PARAM_KEYS | frozenset({"summarizer"})


def _default_summarizer_id() -> str:
    return get_registry().default_for("summarizer") or "llm"


def _instantiate_summarizer(raw: Any, engine: Any | None) -> Any:
    """Create a ``summarizer`` registry plugin and bind the live engine if needed."""
    field = "spec.context_manager.params.summarizer"
    sub = normalize_plugin_binding_lenient(raw, field=field)
    if not plugin_binding_id(sub, field=field):
        sub = {"type": _default_summarizer_id()}
    plugin = get_registry().create("summarizer", sub)
    bind_engine = getattr(plugin, "bind_engine", None)
    if callable(bind_engine):
        bind_engine(engine)
    return plugin


def _bind_summarizer(instance: Any, binding: dict[str, Any], engine: Any | None) -> None:
    bind = getattr(instance, "bind_summarizer", None)
    if not callable(bind):
        return
    params = dict(binding.get("params") or {})
    raw = params.get("summarizer")
    if raw is None:
        raw = _default_summarizer_id()
    bind(_instantiate_summarizer(raw, engine))


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
        _bind_summarizer(instance, binding, engine)
        return instance

    @classmethod
    def create_from_manifest(cls, manifest: dict | None) -> ContextManagerContract:
        return cls.create(manifest=manifest)
