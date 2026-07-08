#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Default-plugin manifests for the runtime registry.

Mirrors ``registry/aliases.py``: a package-shipped ``defaults.yaml`` (the
built-in defaults) can be overridden per-workspace via the ``defaults:``
block in ``config.yaml``. Values from ``config.yaml`` win over the
package defaults on a per-key basis.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from mas.runtime.workspace_config import RuntimeWorkspaceConfig

_DEFAULTS_RESOURCE = "defaults.yaml"
_DEFAULTS_SCHEMA_RESOURCE = "defaults.schema.yaml"


def _load_resource_yaml(resource_name: str) -> dict[str, Any]:
    data = resources.files("mas.runtime").joinpath(resource_name).read_text(encoding="utf-8")
    raw = yaml.safe_load(data) or {}
    return raw if isinstance(raw, dict) else {}


def _load_defaults_mapping(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(key).strip().lower(): str(value) for key, value in raw.items() if str(key).strip() and str(value).strip()}


def _load_defaults_manifest(raw: dict[str, Any]) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    spec = raw.get("spec") or {}
    if isinstance(spec, dict):
        return _load_defaults_mapping(spec)
    return {}


@lru_cache(maxsize=1)
def _defaults_schema() -> dict[str, Any]:
    return _load_resource_yaml(_DEFAULTS_SCHEMA_RESOURCE)


def validate_defaults_manifest(raw: Any, *, name: str = "defaults") -> dict[str, str]:
    """Validate ``raw`` against the ``RuntimeDefaultsManifest`` schema and flatten it.

    ``raw`` may either be a full manifest (``apiVersion``/``kind``/``metadata``/``spec``)
    or a bare mapping of default keys to values (as found under ``defaults:`` in
    ``config.yaml``), which is wrapped into a manifest before validation.
    """
    if isinstance(raw, dict) and {"apiVersion", "kind", "metadata", "spec"}.issubset(raw):
        manifest = raw
    elif isinstance(raw, dict):
        manifest = {
            "apiVersion": "mas/v1",
            "kind": "RuntimeDefaultsManifest",
            "metadata": {"name": name},
            "spec": raw,
        }
    else:
        raise ValueError(f"{name}: defaults manifest must be a mapping")

    try:
        Draft202012Validator(_defaults_schema()).validate(manifest)
    except ValidationError as exc:
        raise ValueError(f"{name}: invalid defaults manifest: {exc.message}") from exc
    return _load_defaults_manifest(manifest)


def load_default_defaults() -> dict[str, str]:
    """Defaults shipped with mas-runtime (``defaults.yaml``)."""
    raw = _load_resource_yaml(_DEFAULTS_RESOURCE)
    return validate_defaults_manifest(raw, name="runtime-default-defaults")


def load_config_defaults(config: RuntimeWorkspaceConfig | None = None) -> dict[str, str]:
    """Workspace overrides from ``config.yaml``'s ``defaults:`` block."""
    ws = config or RuntimeWorkspaceConfig.load()
    return validate_defaults_manifest(ws.defaults, name="workspace-defaults")


def load_defaults(config: RuntimeWorkspaceConfig | None = None) -> dict[str, str]:
    """Package defaults merged with (overridden by) workspace ``config.yaml`` overrides."""
    defaults = load_default_defaults()
    defaults.update(load_config_defaults(config))
    return defaults
