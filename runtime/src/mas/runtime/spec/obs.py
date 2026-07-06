#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pure spec parsers for agent observability — runtime-owned, no ctl dependency."""

from __future__ import annotations

import os
from typing import Any

from mas.runtime.boundary.obs.binding import ObservabilityBinding


class SpecBindingError(ValueError):
    """Agent spec observability binding violates v2 contract."""


def _normalize_obs_plugin(name: str) -> str:
    """Return trimmed plugin id — hyphens normalized to underscores."""
    return (name or "").strip().replace("-", "_")


def _resolve_manifest_cfg_value(cfg: dict[str, Any], key: str, *, default: str = "") -> str:
    """Resolve a manifest config value from inline field or ``{key}_env`` reference."""
    direct = cfg.get(key)
    if direct is not None and str(direct).strip():
        return str(direct).strip()
    env_key = cfg.get(f"{key}_env")
    if env_key:
        return os.environ.get(str(env_key), default).strip()
    return default


def _resolve_path_cfg(cfg: dict[str, Any]) -> str | None:
    """Resolve first non-empty path-like field (inline or env) from plugin config."""
    for key in ("path", "output_path", "events_file", "file_export_path"):
        val = _resolve_manifest_cfg_value(cfg, key)
        if val:
            return val
    return None


def _parse_obs_list(
    items: list[Any],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    plugins: list[str] = []
    configs: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, str):
            plugins.append(_normalize_obs_plugin(item))
        elif isinstance(item, dict):
            for raw_name, cfg in item.items():
                name = _normalize_obs_plugin(str(raw_name))
                plugins.append(name)
                if isinstance(cfg, dict):
                    configs[name] = dict(cfg)
        else:
            raise SpecBindingError(
                f"observability list entries must be str or dict, got {type(item).__name__}"
            )
    return plugins, configs


def parse_obs_spec(raw: list | None) -> ObservabilityBinding:
    """Parse ``spec.observability`` — must be a list or absent."""
    if raw is None:
        return ObservabilityBinding(plugins=[])

    if not isinstance(raw, list):
        raise SpecBindingError(
            f"spec.observability must be a list, got {type(raw).__name__}"
        )

    plugins, configs = _parse_obs_list(raw)

    events_file: str | None = None
    otlp_endpoint_env: str | None = None
    for name, cfg in configs.items():
        path = _resolve_path_cfg(cfg)
        if path and name == "native" and not events_file:
            events_file = path
        if cfg.get("otlp_endpoint_env"):
            otlp_endpoint_env = str(cfg["otlp_endpoint_env"])
    if not otlp_endpoint_env:
        otlp_endpoint_env = "OTEL_EXPORTER_OTLP_ENDPOINT"

    return ObservabilityBinding(
        plugins=plugins,
        plugin_configs=configs,
        otlp_endpoint_env=otlp_endpoint_env,
        events_file=events_file,
    )


__all__ = ["ObservabilityBinding", "SpecBindingError", "parse_obs_spec"]
