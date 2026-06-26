#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Union

logger = logging.getLogger(__name__)

PluginSpec = Union[str, dict[str, Any]]


def _discover_lab_name(yaml_path: Path) -> Optional[str]:
    """Infer the lab name for an experiment YAML from its surrounding context."""
    lab_yaml = yaml_path.parent / "lab-config.yaml"
    if lab_yaml.exists():
        try:
            from mas.runtime.spec.source import load_yaml_file

            _data = load_yaml_file(lab_yaml)
            _lab_section = _data.get("lab", _data) if isinstance(_data, dict) else {}
            _name = _lab_section.get("name")
            if _name:
                return str(_name)
        except Exception:
            logger.debug('suppressed', exc_info=True)

    parent = yaml_path.parent
    if parent.name.endswith(".lab"):
        return parent.name[:-4]

    for parent in yaml_path.parents:
        if parent.name.endswith(".lab"):
            return parent.name[:-4]

    return None


@dataclass
class LabContext:
    """Discovered lab metadata for an experiment or lab YAML file."""

    lab_yaml: Optional[Path] = None
    lab_dir: Optional[Path] = None
    lab_name: Optional[str] = None
    libraries: List[str] = field(default_factory=list)
    plugins: List[PluginSpec] = field(default_factory=list)


def discover_lab_context(yaml_path: Path) -> LabContext:
    """Find sibling ``lab-config.yaml`` and plugin specs for *yaml_path*."""
    ctx = LabContext(lab_dir=yaml_path.parent)
    lab_yaml = yaml_path.parent / "lab-config.yaml"
    if lab_yaml.is_file():
        ctx.lab_yaml = lab_yaml
        try:
            from mas.runtime.spec.source import load_yaml_file

            data = load_yaml_file(lab_yaml)
            section = data.get("lab", data) if isinstance(data, dict) else {}
            if isinstance(section, dict):
                ctx.lab_name = section.get("name") or _discover_lab_name(yaml_path)
                raw_libs = section.get("libraries") or []
                ctx.libraries = [str(x) for x in raw_libs if x]
                raw_plugins = section.get("plugins") or []
                ctx.plugins = [p for p in raw_plugins if p]
        except Exception:
            ctx.lab_name = _discover_lab_name(yaml_path)
    else:
        ctx.lab_name = _discover_lab_name(yaml_path)
    return ctx


def _apply_plugin(plugin: PluginSpec, anchor: Path) -> None:
    """Register one lab plugin — pythonpath or import side-effect."""
    if isinstance(plugin, str):
        candidate = (anchor / plugin).resolve()
        if candidate.is_dir():
            path_str = str(candidate)
            if path_str not in sys.path:
                sys.path.append(path_str)
            return
        try:
            importlib.import_module(plugin)
        except ModuleNotFoundError:
            logger.debug("Lab plugin module %r not found under %s", plugin, anchor)
        return

    if not isinstance(plugin, dict):
        return

    if path_ref := plugin.get("path"):
        candidate = (anchor / str(path_ref)).resolve()
        if candidate.is_dir():
            path_str = str(candidate)
            if path_str not in sys.path:
                sys.path.append(path_str)
        else:
            logger.warning("Lab plugin path not found: %s", candidate)

    if module := plugin.get("module"):
        try:
            importlib.import_module(str(module))
        except ModuleNotFoundError as exc:
            logger.warning("Lab plugin module %r failed to import: %s", module, exc)


def resolve_library_root(ref: str, anchor: Path) -> Path | None:
    """Resolve a ``lab-config.yaml`` libraries entry — scheme name or relative path."""
    from mas.runtime.package_refs import resolve_library_scheme_root

    scheme_root = resolve_library_scheme_root(ref.strip())
    if scheme_root is not None:
        return scheme_root.resolve()

    candidate = (anchor / ref).resolve()
    return candidate if candidate.is_dir() else None


def inject_lab_libraries(lab_context: LabContext) -> None:
    """Add lab directory, library roots, and plugins to ``sys.path`` / imports."""
    if lab_context.lab_dir:
        lab_dir = str(lab_context.lab_dir.resolve())
        if lab_dir not in sys.path:
            sys.path.insert(0, lab_dir)

    anchor = lab_context.lab_yaml.parent if lab_context.lab_yaml else lab_context.lab_dir
    if not anchor:
        return

    for lib_ref in lab_context.libraries:
        lib_path = resolve_library_root(lib_ref, anchor)
        if lib_path is None:
            logger.warning("Lab library not found: %r (anchor %s)", lib_ref, anchor)
            continue
        lib_str = str(lib_path)
        if lib_str not in sys.path:
            sys.path.append(lib_str)

    for plugin in lab_context.plugins:
        _apply_plugin(plugin, anchor)


# Backward-compatible alias
inject_lab_context = inject_lab_libraries
