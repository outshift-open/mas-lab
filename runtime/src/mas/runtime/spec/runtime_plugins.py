#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runtime plugins: gdb debug scripts and checkpoint-store selection.

These sit on snapshot, pause, and persist. Observability and governance
stay in the agent spec.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

_DEBUG_NAMES = frozenset(
    {"debug_script", "gdb", "gov_debug_script", "mas.runtime.debug_script", "mas.gov.debug_script"}
)


def peel_legacy_debug_script(spec: dict[str, Any]) -> None:
    """Move leftover ``spec.governance debug_script`` onto ``spec.debug``."""
    gov = spec.get("governance")
    if not isinstance(gov, list):
        return
    kept: list[Any] = []
    extracted: dict[str, Any] | None = None
    for item in gov:
        name = ""
        cfg: dict[str, Any] = {}
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict) and len(item) == 1:
            raw_name, raw_cfg = next(iter(item.items()))
            name = str(raw_name).strip()
            if isinstance(raw_cfg, dict):
                cfg = dict(raw_cfg)
        if name in _DEBUG_NAMES or name.rsplit(".", 1)[-1] in _DEBUG_NAMES:
            extracted = cfg
            continue
        kept.append(item)
    if extracted is None:
        return
    spec["governance"] = kept
    if not spec.get("debug"):
        spec["debug"] = extracted


def debug_script_wanted(spec: dict[str, Any], enabled_refs: list[str]) -> bool:
    if isinstance(spec.get("debug"), dict):
        return True
    for ref in enabled_refs:
        token = str(ref).strip().lower()
        if token in _DEBUG_NAMES or token.rsplit(".", 1)[-1] in _DEBUG_NAMES:
            return True
    return False


def attach_runtime_plugins(
    kernel_config: Any,
    spec: dict[str, Any],
    *,
    enabled_refs: list[str],
    manifest_dir: Any | None = None,
) -> Any:
    """Instantiate enabled runtime plugins. gdb observes tool-call and tool-result."""
    peel_legacy_debug_script(spec)
    if not debug_script_wanted(spec, enabled_refs):
        return kernel_config
    cfg = dict(spec.get("debug") or {}) if isinstance(spec.get("debug"), dict) else {}
    from mas.runtime.registry import get_registry

    variant = get_registry().resolve_by_type("runtime", "debug_script")
    if variant is None:
        return kernel_config
    plugin_cls = variant.load_class()
    plugin = plugin_cls(
        script=str(cfg.get("script") or ""),
        script_file=str(cfg.get("script_file") or ""),
        manifest_dir=str(manifest_dir or ""),
    )
    existing = tuple(getattr(kernel_config, "runtime_plugins", ()) or ())
    return replace(kernel_config, runtime_plugins=(*existing, plugin))
