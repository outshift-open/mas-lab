#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Project ``config.yaml`` and XDG user config — v2 ctl discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mas.runtime.workspace_config import find_workspace_file, _user_config_path, resolve_config_relative
from mas.runtime.xdg import mas_cache_root, mas_infra_dir
_ENV_INFRA_REFS = "MAS_INFRA_REFS"


def infra_refs_from_env() -> list[str]:
    """Parse ``MAS_INFRA_REFS`` (comma- or space-separated bundle refs).

    When set, overrides ``infra_refs`` from the active workspace config (CLI
    ``--infra-ref`` still wins). Useful for CI and corporate LLM proxies
  without editing workspace files.
    """
    raw = os.environ.get(_ENV_INFRA_REFS, "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    return parts


def merge_infra_refs(
    *,
    mas_refs: list[str],
    workspace_refs: list[str],
    user_refs: list[str] | None = None,
    cli_refs: list[str],
    workspace_found: bool = False,
) -> list[str]:
    """Merge infra refs: MAS < workspace < CLI; user default only if no workspace infra."""
    seen: set[str] = set()
    ordered: list[str] = []
    user_part = [] if (workspace_found and workspace_refs) else list(user_refs or [])
    for ref in mas_refs + workspace_refs + user_part + cli_refs:
        if ref and ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def collect_mas_infra_refs(config: dict[str, Any]) -> list[str]:
    spec = config.get("spec", config)
    raw = spec.get("infra_refs") or spec.get("infra_ref")
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw]
    return list(raw)


def collect_infra_interceptors(config: dict[str, Any]) -> list[str]:
    """Read ``spec.infra_interceptors`` from an agent or MAS manifest."""
    spec = config.get("spec", config)
    raw = spec.get("infra_interceptors") or spec.get("infra_interceptor")
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw]
    return list(raw)


def merge_infra_interceptors(
    *,
    mas_interceptors: list[str],
    workspace_interceptors: list[str],
    cli_interceptors: list[str],
) -> list[str]:
    """Merge interceptor refs: MAS < workspace < CLI (additive, de-duplicated)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in mas_interceptors + workspace_interceptors + cli_interceptors:
        if ref and ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


@dataclass
class WorkspaceConfig:
    _data: dict[str, Any] = field(default_factory=dict)
    _path: Path | None = None
    _config_file: Path | None = None

    @classmethod
    def load(cls, start: Path | None = None) -> WorkspaceConfig:
        path = _find_workspace_file(start or Path.cwd())
        if path is None:
            return cls({})
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return cls({})
        return cls(
            data if isinstance(data, dict) else {},
            path.parent,
            path,
        )

    @property
    def found(self) -> bool:
        return self._path is not None

    @property
    def root(self) -> Path | None:
        return self._path

    @property
    def infra_refs(self) -> list[str]:
        raw = self._data.get("infra_refs") or []
        return [raw] if isinstance(raw, str) else list(raw)

    @property
    def effective_infra_refs(self) -> list[str]:
        """Workspace ``infra_refs`` with ``MAS_INFRA_REFS`` env override."""
        env_refs = infra_refs_from_env()
        if env_refs:
            return env_refs
        return self.infra_refs

    @property
    def infra_interceptors(self) -> list[str]:
        raw = self._data.get("infra_interceptors") or []
        return [raw] if isinstance(raw, str) else list(raw)

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

    @property
    def mas_ctl(self) -> dict[str, Any]:
        raw = self._data.get("mas_ctl") or {}
        return dict(raw) if isinstance(raw, dict) else {}

    @property
    def paths(self) -> dict[str, str]:
        raw = self._data.get("paths") or {}
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    @property
    def config_path(self) -> Path | None:
        return self._config_file

    @property
    def infra_bundle_refs(self) -> list[str]:
        """Workspace infra bundle refs (InfraBundle / LLMProxy paths or library refs)."""
        return self.infra_refs

    @property
    def deployment_name(self) -> str | None:
        dep = self.mas_ctl.get("deployment")
        return str(dep) if dep else None

    @property
    def runtime_id(self) -> str | None:
        rid = self.mas_ctl.get("runtime_id") or self.mas_ctl.get("kernel")
        return str(rid) if rid else None

    @property
    def runtime_profile_path(self) -> Path | None:
        raw = self.mas_ctl.get("runtime_profile")
        if not raw or self._path is None:
            return None
        candidate = (self._path / str(raw)).resolve()
        return candidate if candidate.is_file() else None

    def resolve_library_path(self, lib_ref: str) -> Path | None:
        """Resolve ``team:bundle/sub`` via manifest_libraries."""
        if ":" not in lib_ref:
            return None
        lib, rest = lib_ref.split(":", 1)
        base = self.manifest_libraries.get(lib)
        if not base or self._path is None:
            return None
        root = (self._path / base).resolve()
        candidate = (root / rest).with_suffix(".yaml")
        if candidate.is_file():
            return candidate
        if rest.endswith(".yaml") and (root / rest).is_file():
            return (root / rest).resolve()
        return None


@dataclass
class UserConfig:
    default_infra: str | None = None
    cache_dir: Path = field(default_factory=mas_cache_root)

    @classmethod
    def load(cls) -> UserConfig:
        config_path = _user_config_path()
        if not config_path.is_file():
            return cls(default_infra="standard:production")
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return cls(default_infra="standard:production")
        cache = data.get("cache_dir")
        if not cache and isinstance(data.get("paths"), dict):
            cache = data["paths"].get("cache_dir")
        if cache:
            cache_dir = resolve_config_relative(str(cache), config_path)
        else:
            cache_dir = mas_cache_root()
        return cls(
            default_infra=data.get("default_infra"),
            cache_dir=cache_dir,
        )


def _find_workspace_file(start: Path) -> Path | None:
    return find_workspace_file(start)
