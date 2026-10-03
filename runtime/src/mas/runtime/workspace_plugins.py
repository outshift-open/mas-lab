#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Workspace and lab plugin list from config.yaml / lab.enable_plugins.

``config.yaml`` ``plugins:`` and ``lab-config.yaml`` ``lab.enable_plugins``
turn on gdb, checkpoint stores, and the control wire. Agent YAML still
chooses design_pattern, tools, and models. Empty or all-commented means
nothing extra is on.
"""

from __future__ import annotations

from typing import Any, Iterable

from mas.runtime.harness.catalog import SPEC_IDENTITY_TYPES, WORKSPACE_PLUGIN_TYPES

WORKSPACE_PLUGIN_CATALOG: tuple[tuple[str, str], ...] = (
    ("mas.runtime.debug_script", "gdb breakpoints"),
    ("mas.checkpoint_store.hybrid", "persist to memory and disk"),
    ("mas.checkpoint_store.disk", "JSON files"),
    ("mas.checkpoint_store.memory", "in-process map"),
    ("mas.control_protocol.rpc", "JSON-lines ControlContract wire"),
)


class WorkspacePluginError(ValueError):
    """A config.yaml / lab.enable_plugins entry cannot be applied."""


def catalog_comment_block(*, key: str = "plugins") -> str:
    """Commented YAML catalog. Uncomment ``key:`` and any list item to enable."""
    lines = [
        "# gdb, checkpoint stores, control wire.",
        "# Off unless listed. Uncomment the key and any line to enable.",
        "# Labs may enable the same URNs under lab.enable_plugins.",
        f"# {key}:",
    ]
    width = max(len(urn) for urn, _ in WORKSPACE_PLUGIN_CATALOG)
    for urn, note in WORKSPACE_PLUGIN_CATALOG:
        lines.append(f"#   - {urn:<{width}}  # {note}")
    return "\n".join(lines)


def parse_plugin_refs(raw: Any) -> list[str]:
    """Read ``plugins:`` / ``enable_plugins:``. Missing, null, or all-false is empty."""
    if raw is None:
        return []
    if isinstance(raw, str):
        ref = raw.strip()
        return [ref] if ref else []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif item:
                raise WorkspacePluginError(
                    "plugins entries must be plugin URNs or shortcuts "
                    f"(uncomment a catalog line), got {type(item).__name__}"
                )
        return _dedupe(out)
    if isinstance(raw, dict):
        out = []
        for key, value in raw.items():
            name = str(key).strip()
            if not name:
                continue
            if value is True or value in {"true", "on", "yes", 1}:
                out.append(name)
            elif value is False or value in {"false", "off", "no", 0, None}:
                continue
            else:
                raise WorkspacePluginError(
                    f"plugins.{name} must be true to enable or false/omitted to leave off"
                )
        return _dedupe(out)
    raise WorkspacePluginError(
        "plugins must be a list of URNs (uncomment to enable) or a map of URN: bool"
    )


def apply_workspace_plugins(
    manifest: dict[str, Any] | None,
    refs: Iterable[str],
    *,
    registry: Any | None = None,
) -> dict[str, Any] | None:
    """Enable listed plugins on ``manifest.spec``. Existing spec keys win."""
    ordered = _dedupe(str(item).strip() for item in refs if str(item).strip())
    if not ordered or not isinstance(manifest, dict):
        return manifest
    spec = manifest.setdefault("spec", {})
    if not isinstance(spec, dict):
        raise WorkspacePluginError("agent manifest spec must be a mapping")
    store = registry if registry is not None else _default_registry()
    seen_checkpoint = False
    for ref in ordered:
        entry = _lookup(store, ref)
        if entry is None:
            raise WorkspacePluginError(
                f"unknown workspace plugin {ref!r}; uncomment a catalog URN "
                "from config.yaml or lab.enable_plugins"
            )
        plugin_type = str(entry.attributes.get("plugin_type") or "").strip().lower()
        if plugin_type in SPEC_IDENTITY_TYPES:
            raise WorkspacePluginError(
                f"{ref} is a spec slot ({plugin_type}); set it in agent.yaml, "
                "not config.yaml plugins"
            )
        if plugin_type not in WORKSPACE_PLUGIN_TYPES:
            raise WorkspacePluginError(
                f"{ref} ({plugin_type or 'unknown type'}) cannot be enabled from "
                "config.yaml / lab.enable_plugins"
            )
        short = _short_name(entry, ref)
        if plugin_type == "runtime":
            if short in {"debug_script", "gdb", "gov_debug_script"}:
                spec.setdefault("debug", spec.get("debug") or {})
        elif plugin_type == "checkpoint_store":
            if seen_checkpoint:
                raise WorkspacePluginError(
                    "enable at most one checkpoint_store plugin from config.yaml"
                )
            seen_checkpoint = True
            _apply_checkpoint_store(spec, short)
        elif plugin_type == "control_protocol":
            continue
        else:
            continue
    return manifest


def _default_registry() -> Any:
    from mas.runtime.registry import get_registry

    return get_registry()


def _lookup(registry: Any, ref: str) -> Any | None:
    needle = ref.strip().lower()
    get_entry = getattr(registry, "get_entry", None)
    if callable(get_entry):
        entry = get_entry(ref)
        if entry is not None:
            return entry
    all_entries = getattr(registry, "all_entries", None)
    if not callable(all_entries):
        return None
    for entry in all_entries():
        names = {str(entry.urn).lower(), str(entry.urn).rsplit(".", 1)[-1].lower()}
        names.update(str(alias).strip().lower() for alias in getattr(entry, "shortcuts", ()) or ())
        if needle in names:
            return entry
    return None


def _short_name(entry: Any, ref: str) -> str:
    urn = str(getattr(entry, "urn", "") or ref)
    token = urn.rsplit(".", 1)[-1]
    return token or ref.strip()


def _apply_checkpoint_store(spec: dict[str, Any], kind: str) -> None:
    raw = spec.get("checkpoint")
    if raw is None:
        spec["checkpoint"] = {"storage": {"kind": kind}}
        return
    if not isinstance(raw, dict):
        raise WorkspacePluginError("spec.checkpoint must be an object")
    if raw.get("storage"):
        return
    raw["storage"] = {"kind": kind}


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
