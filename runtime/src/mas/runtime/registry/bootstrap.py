#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest bootstrap for the runtime plugin registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mas.runtime.workspace_config import RuntimeWorkspaceConfig

from . import (
    PluginEntry,
    PluginRegistry,
    VariantInfo,
    _canonical_type_name,
    _normalise_type_name,
    _plugin_type_from_urn,
    _urn_for_type_name,
)
from .aliases import load_aliases
from .defaults import load_defaults

logger = logging.getLogger(__name__)

_BUILTIN_TYPES = {
    "design_pattern",
    "context_manager",
    "context_plugin",
    "memory",
    "governance",
    # The kernel/runtime understands the *shape* of these categories (a
    # pipeline step, an artifact codec) but ships no built-in
    # implementations of its own -- those are pure library plugins (see
    # library-lab's plugin manifests). Pre-registering the type here means
    # a library's plugin manifest doesn't need a redundant `types: [step]`
    # declaration just to register the first one.
    "step",
    "codec",
}

_BUILTIN_RUNTIME_SPEC_KEYS = {
    "design_pattern",
    "context_manager",
    "context_plugin",
}

_BUILTIN_PLUGINS = [
    {
        "type": "design_pattern",
        "urn": "mas.dp.react",
        "description": "ReAct design pattern (native Mealy kernel plugin).",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.runtime.machines.design_pattern.plugins.react",
                "class_name": "ReactPlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "design_pattern",
        "urn": "mas.dp.cot",
        "description": "Chain-of-thought design pattern.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.runtime.machines.design_pattern.plugins.cot",
                "class_name": "CotPlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "design_pattern",
        "urn": "mas.dp.single_pass",
        "description": "Single LLM call without tool loop.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.runtime.machines.design_pattern.plugins.single_pass",
                "class_name": "SinglePassPlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "design_pattern",
        "urn": "mas.dp.introspection",
        "description": "Introspection / reflection over execution log.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.runtime.machines.design_pattern.plugins.introspection",
                "class_name": "IntrospectionPlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "design_pattern",
        "urn": "mas.dp.plan_execute",
        "description": "Plan-then-execute tool scheduling.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.runtime.machines.design_pattern.plugins.plan_execute",
                "class_name": "PlanExecutePlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "design_pattern",
        "urn": "mas.dp.tree_of_thoughts",
        "description": "Tree-of-thoughts multi-pass reasoning.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.runtime.machines.design_pattern.plugins.tree_of_thoughts",
                "class_name": "TreeOfThoughtsPlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "context_manager",
        "urn": "mas.cm.stack",
        "description": "Unbounded or max-messages-capped history (StackConversation).",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.library.standard.plugins.context.conversation",
                "class_name": "StackConversation",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "context_manager",
        "urn": "mas.cm.sliding_window",
        "description": "Fixed-size sliding window over recent exchange pairs.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.library.standard.plugins.context.conversation",
                "class_name": "SlidingWindowConversation",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "context_manager",
        "urn": "mas.cm.summarising",
        "description": "Summarise older turns into a compact system block.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.library.standard.plugins.context.conversation",
                "class_name": "SummarizingConversation",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "context_plugin",
        "urn": "mas.ctx.assembler",
        "description": "Hook-plane context assembler (M_ctx assembly phase).",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.library.standard.plugins.context.assembler",
                "class_name": "ContextAssemblerPlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "memory",
        "urn": "mas.mem.semantic",
        "description": "Semantic memory - FTS/hybrid retrieval and context injection.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.library.standard.plugins.memory.memory_semantic",
                "class_name": "SemanticMemoryPlugin",
                "version": "1.0.0",
            }
        },
    },
    {
        "type": "governance",
        "urn": "mas.gov.sample",
        "description": "Sample governance - HITL on tool egress and tool-result ingress.",
        "default_variant": "builtin",
        "variants": {
            "builtin": {
                "module": "mas.runtime.boundary.gov.sample",
                "class_name": "SampleGovernancePlugin",
                "version": "1.0.0",
            }
        },
    },
]


@dataclass
class _ManifestPluginCandidate:
    plugin_type: str
    urn: str
    default_variant: str
    variants: dict[str, VariantInfo]
    shortcuts: list[str] = field(default_factory=list)
    description: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    provides_types: set[str] = field(default_factory=set)


def _variant_info_from_data(vdata: dict[str, Any]) -> VariantInfo:
    return VariantInfo(
        module=str(vdata.get("module") or ""),
        class_name=str(vdata.get("class") or vdata.get("class_name") or ""),
        version=str(vdata.get("version") or ""),
        description=str(vdata.get("description") or ""),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _parse_generic_manifest(
    data: dict[str, Any],
) -> tuple[
    set[str],
    list[_ManifestPluginCandidate],
    dict[str, str],
    dict[str, str],
    set[str],
]:
    known_types: set[str] = set()
    candidates: list[_ManifestPluginCandidate] = []
    role_aliases: dict[str, str] = {}
    defaults: dict[str, str] = {}
    runtime_spec_keys: set[str] = set()

    for type_name in data.get("types") or []:
        known_types.add(_canonical_type_name(str(type_name)))

    for item in data.get("plugins") or []:
        if not isinstance(item, dict):
            continue
        candidate = _candidate_from_manifest_item(item)
        if candidate is not None:
            # NOTE: deliberately NOT adding candidate.plugin_type to
            # known_types here. A candidate's own declared `type:` must be
            # gated through the fixpoint like everything else — it becomes
            # registerable only once it's a builtin type, listed in this
            # manifest's own `types:`, or unlocked by another candidate's
            # `provides_types`. Auto-whitelisting a candidate's type just
            # because it showed up in `plugins:` would make `provides_types`
            # meaningless (every type would already be "known" before the
            # fixpoint even starts) and would silently accept a typo'd
            # `type:` as a brand new category instead of catching it.
            candidates.append(candidate)

    aliases = data.get("aliases") or data.get("role_aliases") or {}
    if isinstance(aliases, dict):
        for role, urn in aliases.items():
            role_aliases[str(role)] = str(urn)

    manifest_defaults = data.get("defaults") or {}
    if isinstance(manifest_defaults, dict):
        for spec_key, plugin_id in manifest_defaults.items():
            defaults[_canonical_type_name(str(spec_key))] = str(plugin_id)

    for spec_key in data.get("runtime_spec_keys") or []:
        runtime_spec_keys.add(_canonical_type_name(str(spec_key)))

    return known_types, candidates, role_aliases, defaults, runtime_spec_keys


def _candidate_from_target(
    plugin_type: str,
    name: str,
    target: str,
    *,
    attrs: dict[str, Any] | None = None,
) -> _ManifestPluginCandidate:
    module_path, _, class_name = str(target).rpartition(":")
    return _ManifestPluginCandidate(
        plugin_type=str(plugin_type),
        urn=_urn_for_type_name(plugin_type, name),
        default_variant="builtin",
        variants={"builtin": VariantInfo(module=module_path, class_name=class_name)},
        shortcuts=[str(name)],
        description="",
        attributes=dict(attrs or {}),
        provides_types=set(),
    )


def _candidate_from_manifest_item(item: dict[str, Any]) -> _ManifestPluginCandidate | None:
    plugin_type = str(item.get("type") or "").strip()
    if not plugin_type:
        return None

    name = str(item.get("name") or "").strip()
    urn = str(item.get("urn") or "").strip() or _urn_for_type_name(plugin_type, name)

    variants: dict[str, VariantInfo] = {}
    raw_variants = item.get("variants") or {}
    if isinstance(raw_variants, dict) and raw_variants:
        for variant_name, variant_data in raw_variants.items():
            if isinstance(variant_data, dict):
                variants[str(variant_name)] = _variant_info_from_data(variant_data)
    else:
        module = item.get("module")
        class_name = item.get("class") or item.get("class_name")
        if module and class_name:
            variants["builtin"] = VariantInfo(module=str(module), class_name=str(class_name))
    if not variants:
        return None

    return _ManifestPluginCandidate(
        plugin_type=plugin_type,
        urn=urn,
        default_variant=str(item.get("default") or "builtin"),
        variants=variants,
        shortcuts=[str(s) for s in (item.get("shortcuts") or ([name] if name else []))],
        description=str(item.get("description") or ""),
        attributes=dict(item.get("attributes") or {}),
        provides_types={_canonical_type_name(str(t)) for t in (item.get("provides_types") or [])},
    )


def _register_candidates_fixpoint(
    reg: PluginRegistry,
    known_types: set[str],
    candidates: list[_ManifestPluginCandidate],
) -> None:
    pending = list(candidates)
    while pending:
        next_pending: list[_ManifestPluginCandidate] = []
        progressed = False
        for candidate in pending:
            canonical = _canonical_type_name(candidate.plugin_type)
            if canonical not in known_types:
                next_pending.append(candidate)
                continue
            reg.register_type(canonical)
            reg.register(
                PluginEntry(
                    urn=candidate.urn,
                    description=candidate.description,
                    default_variant=candidate.default_variant,
                    shortcuts=list(candidate.shortcuts),
                    variants=dict(candidate.variants),
                    attributes={"plugin_type": canonical, **dict(candidate.attributes)},
                )
            )
            known_types.update(candidate.provides_types)
            for provided in candidate.provides_types:
                reg.register_type(provided)
            progressed = True
        if not progressed:
            unresolved = sorted(
                f"{candidate.urn} (type={candidate.plugin_type!r})" for candidate in next_pending
            )
            raise ValueError(
                "Unresolved plugin manifest entries after fixpoint — the following "
                "plugin types never became known (typo'd `type:`/`provides_types:` "
                f"field, or a missing manifest entry?): {'; '.join(unresolved)}"
            )
        pending = next_pending


def load_registry(config: RuntimeWorkspaceConfig | None = None) -> PluginRegistry:
    reg = PluginRegistry()

    _register_builtin_plugins(reg)

    for alias, urn in load_aliases(config).items():
        reg.register_alias(alias, urn)
    reg.validate_aliases()

    reg.register_types(_BUILTIN_TYPES)
    reg.register_runtime_spec_keys(_BUILTIN_RUNTIME_SPEC_KEYS)
    # "model" is a default LLM model id, not a registry plugin type/spec_key
    # -- exposed separately via mas.runtime.agent_defaults.default_model().
    for spec_key, plugin_id in load_defaults(config).items():
        if spec_key == "model":
            continue
        reg.set_default(spec_key, plugin_id)

    _register_library_plugins(reg)
    return reg


def _register_library_plugins(reg: PluginRegistry) -> None:
    """Discover and register plugins declared by libraries (steps, codecs,
    and anything else a library chooses to expose), on top of the built-in
    catalog above.

    This is the "know which plugins should be registered in runtime and lab
    libraries" mechanism: every library root discovered by
    :func:`mas.library_roots.discover_library_roots` (installed packages via
    the ``mas.runtime.manifest_libraries`` entry point, workspace
    ``manifest_libraries:`` config, and ``library.yaml`` directory scan) is
    checked for plugin manifests via :func:`mas.library_catalog.
    discover_plugin_manifests`, and each one is registered through the same
    generic fixpoint loader used for built-ins (see
    :func:`register_manifest_file`). A manifest can declare
    ``provides_types`` so a plugin from one library can introduce a brand
    new plugin *type* that a plugin from another library (or a later
    manifest) then registers against — no code change to this module is
    needed to add a new category.

    Manifest errors are not swallowed: a typo'd ``type:``/``module:``/
    ``class:`` in a library's plugin manifest is a real configuration
    error and should fail loudly at startup (see :func:`register_manifest_file`
    / :func:`_register_candidates_fixpoint`), not silently leave a plugin
    unregistered until something downstream fails with a confusing error.
    """
    from mas.library_catalog import discover_plugin_manifests

    for manifest_path in discover_plugin_manifests():
        try:
            register_manifest_file(reg, manifest_path)
        except Exception as exc:
            raise ValueError(
                f"Failed to register plugin manifest {manifest_path}: {exc}"
            ) from exc


def _register_builtin_plugins(reg: PluginRegistry) -> None:
    # Defaults are set once in load_registry() via load_defaults(config), which
    # has access to the workspace config; this function only registers the
    # built-in plugin catalog itself.
    reg.register_runtime_spec_keys(set(_BUILTIN_RUNTIME_SPEC_KEYS))
    for entry in _BUILTIN_PLUGINS:
        reg.register_type(str(entry["type"]))
        variants = {
            vname: VariantInfo(
                module=vdata["module"],
                class_name=vdata["class_name"],
                version=vdata.get("version", ""),
                description=vdata.get("description", ""),
            )
            for vname, vdata in (entry.get("variants") or {}).items()
        }
        reg.register(
            PluginEntry(
                urn=str(entry["urn"]),
                description=str(entry.get("description") or ""),
                default_variant=str(entry.get("default_variant") or "builtin"),
                variants=variants,
                attributes={"plugin_type": str(entry["type"])},
            )
        )


def register_plugin(
    reg: PluginRegistry,
    urn: str,
    cls: type,
    *,
    shortcuts: list[str] | None = None,
    variant: str = "builtin",
    description: str = "",
    attributes: dict[str, Any] | None = None,
) -> None:
    raw_plugin_type = (attributes or {}).get("plugin_type")
    plugin_type = _normalise_type_name(str(raw_plugin_type)) if raw_plugin_type else _plugin_type_from_urn(urn)
    if plugin_type:
        reg.register_type(plugin_type)
    entry = reg._entries.get(urn)
    module = cls.__module__
    class_name = cls.__name__
    if entry is None:
        entry = PluginEntry(
            urn=urn,
            description=description,
            default_variant=variant,
            shortcuts=shortcuts or [],
            variants={},
            attributes={"plugin_type": plugin_type, **dict(attributes or {})},
        )
        reg.register(entry)
    elif attributes:
        entry.attributes.update(attributes)
    entry.variants[variant] = VariantInfo(module=module, class_name=class_name)
    if shortcuts:
        for shortcut in shortcuts:
            reg.register_alias(shortcut, urn)


def register_manifest_data(reg: PluginRegistry, manifest_data: dict[str, Any]) -> None:
    known_types, candidates, role_aliases, defaults, runtime_spec_keys = _parse_generic_manifest(manifest_data)
    merged_known_types = set(reg._known_types)
    merged_known_types.update(known_types)
    reg.register_types(known_types)
    reg.register_runtime_spec_keys(runtime_spec_keys)
    for spec_key, plugin_id in defaults.items():
        reg.set_default(spec_key, plugin_id)
    _register_candidates_fixpoint(reg, merged_known_types, candidates)
    for role, urn in role_aliases.items():
        reg.register_alias(role, urn)


def register_manifest_file(reg: PluginRegistry, path: str | Path) -> None:
    register_manifest_data(reg, _load_yaml(Path(path)))
