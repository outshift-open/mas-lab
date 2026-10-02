#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Authoritative component registry — runtime, placement, framework IDs."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

@dataclass(frozen=True)
class ComponentEntry:
    id: str
    layer: str
    module: str | None = None
    description: str = ""
    status: str = "available"
    availability_check: str | None = None


class UnknownComponentError(KeyError):
    pass


def _dev_registry_paths() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    ctl_root = module_dir.parents[4]
    repo_root = module_dir.parents[5]
    return [
        ctl_root / "docs" / "schemas" / "component-registry.yaml",
        repo_root / "docs" / "schemas" / "component-registry.yaml",
    ]


def _load_registry_text() -> str | None:
    try:
        from importlib.resources import as_file, files

        resource = files("mas.ctl").joinpath("_schemas", "component-registry.yaml")
        with as_file(resource) as path:
            if path.is_file():
                return path.read_text(encoding="utf-8")
    except Exception:
        pass

    for path in _dev_registry_paths():
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, list[ComponentEntry]]:
    text = _load_registry_text()
    if text is None:
        return {"runtimes": [], "placement": [], "framework": []}
    raw = yaml.safe_load(text) or {}
    spec = raw.get("spec") or {}
    out: dict[str, list[ComponentEntry]] = {}
    for key in ("runtimes", "placement", "framework"):
        items = spec.get(key) or []
        out[key] = [
            ComponentEntry(
                id=str(item["id"]),
                layer=str(item.get("layer", key)),
                module=item.get("module"),
                description=str(item.get("description", "")),
                status=str(item.get("status", "available")),
                availability_check=item.get("availability_check"),
            )
            for item in items
            if isinstance(item, dict) and item.get("id")
        ]
    return out


_UNAVAILABLE_STATUSES = frozenset({"planned", "future_release"})
_SECTION_LABEL = {
    "runtimes": "runtime",
    "placement": "placement",
    "framework": "framework",
}


def _by_id(section: str) -> dict[str, ComponentEntry]:
    return {e.id: e for e in _load_catalog().get(section, [])}


def _availability_unlocked(entry: ComponentEntry) -> bool:
    """A planned catalog row can unlock when its optional package is importable."""
    module = (entry.availability_check or "").strip()
    if not module:
        return False
    try:
        importlib.import_module(module)
    except ImportError:
        return False
    return True


def get_component(section: str, component_id: str) -> ComponentEntry:
    """Return one catalog entry, including planned IDs."""
    label = _SECTION_LABEL.get(section, section)
    entry = _by_id(section).get(component_id)
    if entry is None:
        raise UnknownComponentError(f"unknown {label} id: {component_id!r}")
    return entry


def validate_component_id(section: str, component_id: str, label: str | None = None) -> str:
    """Return an available component ID or reject planned/unknown entries."""
    resolved = label or _SECTION_LABEL.get(section, section)
    entry = get_component(section, component_id)
    if entry.status in _UNAVAILABLE_STATUSES and not _availability_unlocked(entry):
        raise UnknownComponentError(f"{resolved} {component_id!r} is not available yet")
    return entry.id


def get_runtime(runtime_id: str) -> ComponentEntry:
    return get_component("runtimes", runtime_id)


def list_runtime_ids(*, include_planned: bool = False) -> list[str]:
    items = _load_catalog().get("runtimes", [])
    if include_planned:
        return [e.id for e in items]
    return [e.id for e in items if e.status not in _UNAVAILABLE_STATUSES]


def list_runtimes() -> list[ComponentEntry]:
    return list(_load_catalog().get("runtimes", []))


def list_placement_ids() -> list[str]:
    return [
        e.id
        for e in _load_catalog().get("placement", [])
        if e.status not in _UNAVAILABLE_STATUSES or _availability_unlocked(e)
    ]


def get_placement(placement_id: str) -> ComponentEntry:
    """Return the catalog entry for one placement strategy, including planned IDs."""
    return get_component("placement", placement_id)


def validate_placement_id(placement_id: str) -> str:
    """Return an available placement ID or reject planned/unknown entries."""
    return validate_component_id("placement", placement_id)


def list_framework_ids() -> list[str]:
    return [e.id for e in _load_catalog().get("framework", []) if e.status not in _UNAVAILABLE_STATUSES]


def get_framework(framework_id: str) -> ComponentEntry:
    """Return the catalog entry for one framework adapter, including planned IDs."""
    return get_component("framework", framework_id)


def validate_framework_id(framework_id: str) -> str:
    """Return an available framework ID or reject planned/unknown entries."""
    return validate_component_id("framework", framework_id)


def import_class(dotted: str) -> type:
    module_name, _, attr = dotted.rpartition(".")
    if not module_name or not attr:
        raise ValueError(f"invalid module path: {dotted!r}")
    mod = importlib.import_module(module_name)
    cls = getattr(mod, attr, None)
    if cls is None:
        raise ImportError(f"{attr} not found in {module_name}")
    return cls


def validate_runtime_id(runtime_id: str) -> str:
    return validate_component_id("runtimes", runtime_id)


def registry_path() -> Path:
    for path in _dev_registry_paths():
        if path.is_file():
            return path
    try:
        from importlib.resources import as_file, files

        resource = files("mas.ctl").joinpath("_schemas", "component-registry.yaml")
        with as_file(resource) as path:
            return Path(path)
    except Exception:
        return _dev_registry_paths()[0]
