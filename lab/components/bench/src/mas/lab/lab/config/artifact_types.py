#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Artifact type contract — implementations are library.yaml plugins.

Libraries declare ``type: artifact`` entries (name, module, class) in
``library.yaml``.  Path and format live on the class.  Bench looks them
up through ``mas.runtime.registry``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mas.runtime.registry import PluginEntry, get_registry, register_plugin


class ArtifactType:
    """Named artifact kind.  Subclasses set ``path`` / ``format``."""

    path: str = "{level_dir}/{name}"
    format: str = ""
    description: str = ""
    schema: str | None = None


def _urn(name: str) -> str:
    token = str(name).strip().lower().replace("-", "_").replace(".", "_")
    return f"mas.artifact.{token}"


def _info_from_entry(entry: PluginEntry) -> dict[str, Any]:
    cls = entry.resolve().load_class()
    attrs = entry.attributes or {}
    info: dict[str, Any] = {
        "path": attrs.get("path") or getattr(cls, "path", None) or "{level_dir}/{name}",
        "format": attrs.get("format") or getattr(cls, "format", None) or "",
        "description": (
            entry.description
            or attrs.get("description")
            or getattr(cls, "description", None)
            or ""
        ),
    }
    schema = attrs.get("schema") or getattr(cls, "schema", None)
    if schema:
        info["schema"] = schema
    return info


def _named_entry(name: str) -> PluginEntry | None:
    key = str(name).strip().lower()
    for entry in get_registry().get_by_category("artifact"):
        shortcuts = {str(s).lower() for s in entry.shortcuts}
        if key in shortcuts or entry.urn.lower() == _urn(name).lower():
            return entry
    return None


def type_info(name: str) -> Dict[str, Any]:
    """Return path/format/description for one artifact type, or ``{}``."""
    entry = _named_entry(name)
    return _info_from_entry(entry) if entry is not None else {}


def list_artifact_types() -> Dict[str, Dict[str, Any]]:
    """Return artifact types declared in library manifests."""
    items: Dict[str, Dict[str, Any]] = {}
    for entry in get_registry().get_by_category("artifact"):
        name = str(entry.shortcuts[0]) if entry.shortcuts else entry.urn.rsplit(".", 1)[-1]
        if name:
            items[name] = _info_from_entry(entry)
    return dict(sorted(items.items()))


def register_artifact_type(
    name: str,
    path: str,
    format: str = "json",
    description: str = "",
    schema: Optional[str] = None,
) -> None:
    """Register an artifact type in this process.

    Libraries declare types in ``library.yaml`` (``type: artifact``).
    Call this to add a type without a manifest (tests).
    """
    attrs: dict[str, Any] = {
        "plugin_type": "artifact",
        "path": path,
        "format": format,
    }
    if schema:
        attrs["schema"] = schema
    register_plugin(
        _urn(name),
        ArtifactType,
        shortcuts=[name],
        description=description,
        attributes=attrs,
    )
