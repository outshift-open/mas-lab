#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Pure spec parser for ``spec.context_sources`` — same plugin-list shape as
``spec.observability`` (see ``mas.runtime.spec.obs``).

Currently the only consumer is library-skills, which reads the first plugin
id to pick the skill-plugin engine (native, adk, langchain), and an optional
per-plugin ``auto_inject: true`` to also auto-grant run-skill-script (script
execution) alongside the always-auto-granted read-only skill-access tools —
see ctl/src/mas/ctl/session/bootstrap.py's _resolve_skill_plugin_config /
_auto_inject_skill_tools. The shape is kept generic so other ContextContract
source plugins can register here in the future without a schema change.
"""

from __future__ import annotations

from typing import Any


class SpecBindingError(ValueError):
    """Agent spec context_sources binding violates the v2 contract."""


def _normalize_plugin_id(name: str) -> str:
    return (name or "").strip().replace("-", "_")


def parse_context_sources(raw: Any) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Parse ``spec.context_sources`` into (plugin_ids, plugin_configs).

    Accepted shapes, mirroring ``spec.observability``::

        context_sources:
          - native
        context_sources:
          - native:
              base_dir: ./skills/
    """
    if raw is None:
        return [], {}
    if not isinstance(raw, list):
        raise SpecBindingError(
            f"spec.context_sources must be a list, got {type(raw).__name__}"
        )

    plugins: list[str] = []
    configs: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, str):
            plugins.append(_normalize_plugin_id(item))
        elif isinstance(item, dict):
            for raw_name, cfg in item.items():
                name = _normalize_plugin_id(str(raw_name))
                plugins.append(name)
                if isinstance(cfg, dict):
                    configs[name] = dict(cfg)
        else:
            raise SpecBindingError(
                f"context_sources list entries must be str or dict, got {type(item).__name__}"
            )
    return plugins, configs


__all__ = ["parse_context_sources", "SpecBindingError"]
