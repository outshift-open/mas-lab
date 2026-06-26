#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Minimal mas-workspace.yaml discovery for runtime (no mas-ctl import)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_WORKSPACE_FILE = "mas-workspace.yaml"


def find_workspace_file(start: Path | None = None) -> Path | None:
    """Return path to ``mas-workspace.yaml`` walking up from *start*."""
    env_root = os.environ.get("MAS_WORKSPACE_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve() / _WORKSPACE_FILE
        return candidate if candidate.is_file() else None

    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / _WORKSPACE_FILE
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break

    global_cfg = Path.home() / ".mas" / _WORKSPACE_FILE
    return global_cfg if global_cfg.is_file() else None


@dataclass
class RuntimeWorkspaceConfig:
    """Subset of workspace fields needed by mas-runtime."""

    _data: dict[str, Any] = field(default_factory=dict)
    _path: Path | None = None

    @classmethod
    def load(cls, start: Path | None = None) -> RuntimeWorkspaceConfig:
        path = find_workspace_file(start)
        if path is None:
            return cls({})
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return cls({})
        return cls(data if isinstance(data, dict) else {}, path.parent)

    @property
    def found(self) -> bool:
        return self._path is not None

    @property
    def root(self) -> Path | None:
        return self._path

    @property
    def manifest_libraries(self) -> dict[str, str]:
        raw = self._data.get("manifest_libraries") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    @property
    def default_model(self) -> str | None:
        defaults = self._data.get("defaults") or {}
        if isinstance(defaults, dict):
            model = defaults.get("model")
            return str(model) if model else None
        return None
