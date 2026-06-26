#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Lab workspace helpers — mas-workspace.yaml accessors (not runtime shims)."""


from pathlib import Path
from typing import Any

from mas.ctl.workspace.config import WorkspaceConfig, _find_workspace_file


def workspace_get(ws: WorkspaceConfig, tool: str, key: str, fallback: Any = None) -> Any:
    return (getattr(ws, "_data", {}) or {}).get(tool, {}).get(key, fallback)


def workspace_resolve_path(ws: WorkspaceConfig, tool: str, key: str) -> Path | None:
    raw = workspace_get(ws, tool, key)
    root = getattr(ws, "_path", None) or getattr(ws, "root", None)
    if raw is None or root is None:
        return None
    p = Path(str(raw)).expanduser()
    if p.is_absolute():
        return p
    return (Path(root) / p).resolve()


_find_config = _find_workspace_file


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Find workspace root by walking up to ``mas-workspace.yaml``."""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "mas-workspace.yaml").exists():
            return directory
    return None


__all__ = [
    "WorkspaceConfig",
    "find_workspace_root",
    "workspace_get",
    "workspace_resolve_path",
    "_find_config",
    "_find_workspace_file",
]
