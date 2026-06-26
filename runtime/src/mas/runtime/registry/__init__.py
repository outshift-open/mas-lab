#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Plugin URN registry — single runtime entry point for manifest ``spec.*`` resolution."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent / "plugin_registry.yaml"

# Agent manifest ``spec.<key>`` → registry resolution type (also URN category).
SPEC_KEYS: dict[str, str] = {
    "design_pattern": "design_pattern",
    "context_manager": "context_manager",
    "context_plugin": "context_plugin",
}

SPEC_DEFAULTS: dict[str, str] = {
    "design_pattern": "react@v1",
    "context_manager": "sliding-window",
}

# Resolution type / alias → URN prefix (mas.<cat>.)
_TYPE_PREFIX = {
    "dp": "mas.dp.",
    "design_pattern": "mas.dp.",
    "design-pattern": "mas.dp.",
    "cm": "mas.cm.",
    "context_manager": "mas.cm.",
    "context-manager": "mas.cm.",
    "ctx": "mas.ctx.",
    "context_plugin": "mas.ctx.",
}

_SPEC_KEY_CATEGORY = {
    "design_pattern": "dp",
    "context_manager": "cm",
    "context_plugin": "ctx",
}


@dataclass
class VariantInfo:
    module: str
    class_name: str
    version: str = ""
    description: str = ""

    def load_class(self) -> type:
        mod = importlib.import_module(self.module)
        return getattr(mod, self.class_name)


@dataclass
class PluginEntry:
    urn: str
    description: str = ""
    default_variant: str = "builtin"
    shortcuts: list[str] = field(default_factory=list)
    variants: dict[str, VariantInfo] = field(default_factory=dict)

    @property
    def default(self) -> VariantInfo | None:
        return self.variants.get(self.default_variant)

    def resolve(self, variant: str = "") -> VariantInfo:
        key = variant or self.default_variant
        if key not in self.variants:
            raise ValueError(
                f"Unknown variant {key!r} for {self.urn}. "
                f"Available: {list(self.variants)}"
            )
        return self.variants[key]


class PluginRegistry:
    """Runtime plugin catalog — query via manifest ``spec.<key>`` names."""

    _dp_instances: dict[str, Any]

    def __init__(self) -> None:
        self._entries: dict[str, PluginEntry] = {}
        self._shortcuts: dict[str, str] = {}
        self._role_aliases: dict[str, str] = {}
        self._scan_paths: list[Path] = []
        self._dp_instances = {}

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, entry: PluginEntry) -> None:
        self._entries[entry.urn] = entry
        for sc in entry.shortcuts:
            self._shortcuts[sc.lower()] = entry.urn

    def register_role_alias(self, role: str, urn: str) -> None:
        self._role_aliases[role.lower()] = urn

    # ── Resolution (manifest spec bindings) ──────────────────────────────

    @staticmethod
    def binding_plugin_id(binding: dict[str, Any] | None, *, spec_key: str) -> str:
        """Extract ``type`` or ``ref`` from a ``spec.<key>`` object."""
        raw = binding or {}
        return str(raw.get("type") or raw.get("ref") or SPEC_DEFAULTS.get(spec_key, ""))

    def resolve_spec(
        self,
        spec_key: str,
        binding: dict[str, Any] | None = None,
    ) -> VariantInfo:
        """Resolve ``spec.<spec_key>`` binding to a :class:`VariantInfo`."""
        plugin_type = SPEC_KEYS.get(spec_key, spec_key)
        name = self.binding_plugin_id(binding, spec_key=spec_key)
        info = self.resolve_by_type(plugin_type, name)
        if info is None:
            raise KeyError(
                f"no plugin registered for spec.{spec_key} "
                f"type/ref={name!r}"
            )
        return info

    def create(
        self,
        spec_key: str,
        binding: dict[str, Any] | None = None,
        *,
        manifest: dict | None = None,
        **params: Any,
    ) -> Any:
        """Instantiate the plugin declared under ``spec.<spec_key>``."""
        if binding is None and manifest is not None:
            raw = (manifest.get("spec") or {}).get(spec_key) or {}
            binding = raw if isinstance(raw, dict) else {}
        binding = dict(binding or {})
        info = self.resolve_spec(spec_key, binding)
        cls = info.load_class()
        ctor_params = {**dict(binding.get("params") or {}), **params}
        try:
            return cls(**ctor_params)
        except TypeError as exc:
            raise TypeError(
                f"PluginRegistry.create({spec_key!r}): {cls.__name__}(**{ctor_params!r}) failed"
            ) from exc

    def get_design_pattern(self, plugin_id: str | None = None) -> Any:
        """Cached Mealy design-pattern plugin instance (kernel hot path)."""
        key = plugin_id or SPEC_DEFAULTS["design_pattern"]
        if key not in self._dp_instances:
            info = self.resolve_by_type("design_pattern", key)
            if info is None:
                raise KeyError(f"unknown design pattern plugin: {key!r}")
            self._dp_instances[key] = info.load_class()()
        return self._dp_instances[key]

    def resolve(self, name: str, variant: str = "") -> VariantInfo | None:
        key = name.lower()
        if key in self._entries:
            return self._entries[key].resolve(variant)
        urn = self._shortcuts.get(key) or self._role_aliases.get(key)
        if urn and urn in self._entries:
            return self._entries[urn].resolve(variant)
        return None

    def resolve_by_type(self, plugin_type: str, name: str) -> VariantInfo | None:
        prefix = _TYPE_PREFIX.get(plugin_type.lower().replace("_", "-"))
        if not prefix:
            return self.resolve(name)
        urn = self.urn_for(name)
        if urn and urn.startswith(prefix):
            return self.resolve(name)
        candidate = prefix + name.lower().replace("-", "_")
        if candidate in self._entries:
            return self._entries[candidate].resolve()
        return None

    def urn_for(self, name: str) -> str | None:
        key = name.lower()
        if key in self._entries:
            return key
        return self._shortcuts.get(key) or self._role_aliases.get(key)

    # ── Query (UI / CLI / lab delegation) ────────────────────────────────

    def list(self, spec_key: str | None = None) -> list[dict[str, Any]]:
        """List plugins; *spec_key* matches agent manifest ``spec.<key>``."""
        if spec_key is None:
            return self._entries_as_dicts(
                [self._entries[u] for u in self.list_all()]
            )
        category = _SPEC_KEY_CATEGORY.get(spec_key, spec_key)
        return self._entries_as_dicts(self.get_by_category(category))

    def list_all(self) -> list[str]:
        return sorted(self._entries)

    def list_categories(self) -> list[str]:
        cats: set[str] = set()
        for urn in self._entries:
            parts = urn.split(".")
            if len(parts) >= 3:
                cats.add(parts[1])
        return sorted(cats)

    def get_by_category(self, category: str) -> list[PluginEntry]:
        cat = category.lower().replace("_", "-")
        if cat in ("design-pattern", "designpattern"):
            cat = "dp"
        if cat in ("context-manager", "contextmanager"):
            cat = "cm"
        if cat in ("context-plugin", "contextplugin"):
            cat = "ctx"
        prefix = f"mas.{cat}."
        return [entry for urn, entry in sorted(self._entries.items()) if urn.startswith(prefix)]

    @staticmethod
    def _entries_as_dicts(entries: list[PluginEntry]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entry in entries:
            default = entry.default
            items.append(
                {
                    "urn": entry.urn,
                    "description": entry.description,
                    "shortcuts": list(entry.shortcuts),
                    "category": entry.urn.split(".")[1] if entry.urn.count(".") >= 2 else "",
                    "module": default.module if default else "",
                    "class_name": default.class_name if default else "",
                }
            )
        return items

    def all_shortcuts(self) -> dict[str, str]:
        merged = dict(self._shortcuts)
        merged.update(self._role_aliases)
        return merged

    def add_scan_path(self, path: Path | str) -> None:
        self._scan_paths.append(Path(path))


_instance: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Single runtime registry entry point.

    Process-wide singleton: safe to call from any kernel instance, but not safe
    to mutate concurrently without external locking. Each :class:`RuntimeKernel`
    caches its design-pattern plugin at construction time; do not rebind or
    replace the registry mid-feed.
    """
    global _instance
    if _instance is None:
        _instance = _load_registry()
    return _instance


def _load_registry() -> PluginRegistry:
    reg = PluginRegistry()
    if not _REGISTRY_PATH.exists():
        logger.warning("Plugin registry not found: %s", _REGISTRY_PATH)
        return reg
    try:
        import yaml

        with open(_REGISTRY_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("Failed to load plugin registry: %s", exc)
        return reg

    for section in ("design_patterns", "context_managers", "context_plugins", "memory", "governance"):
        for urn, info in (data.get(section) or {}).items():
            if not isinstance(info, dict):
                continue
            variants: dict[str, VariantInfo] = {}
            for vname, vdata in (info.get("variants") or {}).items():
                if isinstance(vdata, dict):
                    variants[vname] = VariantInfo(
                        module=vdata.get("module", ""),
                        class_name=vdata.get("class", ""),
                        version=vdata.get("version", ""),
                    )
            reg.register(
                PluginEntry(
                    urn=urn,
                    description=info.get("description", ""),
                    default_variant=info.get("default", "builtin"),
                    shortcuts=info.get("shortcuts", []),
                    variants=variants,
                )
            )

    for role, target_urn in (data.get("role_aliases") or {}).items():
        reg.register_role_alias(role, target_urn)

    return reg


def register_plugin(
    urn: str,
    cls: type,
    *,
    shortcuts: list[str] | None = None,
    variant: str = "builtin",
    description: str = "",
) -> None:
    """Register a plugin class at runtime (tests / extensions)."""
    reg = get_registry()
    module = cls.__module__
    class_name = cls.__name__
    entry = reg._entries.get(urn)
    if entry is None:
        entry = PluginEntry(
            urn=urn,
            description=description,
            default_variant=variant,
            shortcuts=shortcuts or [],
            variants={},
        )
        reg.register(entry)
    entry.variants[variant] = VariantInfo(module=module, class_name=class_name)
    if shortcuts:
        for sc in shortcuts:
            reg._shortcuts[sc.lower()] = urn


def add_plugin_path(path: str) -> None:
    get_registry().add_scan_path(path)


__all__ = [
    "SPEC_DEFAULTS",
    "SPEC_KEYS",
    "PluginEntry",
    "PluginRegistry",
    "VariantInfo",
    "add_plugin_path",
    "get_registry",
    "register_plugin",
]
