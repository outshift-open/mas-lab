#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``inputs.tool_fixtures``: generic mapping layer over free-form tool payloads.

The dataset declares *which tool gets which payload*; mas-lab resolves that
mapping to ``{"by_tool": {tool | "*": payload}}`` and hands it to tools via
``ctx.tool_fixtures`` (read with ``mas.runtime.contracts.tool_fixture``).
Payload bodies are owned and validated by the tools, never by mas-lab.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mas.lab.inputs.refs import is_ref_object, load_ref, resolve_file_slot

SHARED = "*"


def _resolve_payload(spec: Any, base_path: Optional[Path]) -> Any:
    if isinstance(spec, str) or is_ref_object(spec):
        return resolve_file_slot(spec, base_path)
    return spec


def resolve_tool_fixtures(value: Any, base_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Resolve a dataset ``tool_fixtures`` declaration to ``{"by_tool": {...}}``.

    Accepted mapping forms: a path or ``{ref:}`` (shared by every tool), a
    ``by_tool`` mapping (path, ``{ref:}``, or inline payload per tool), or a
    list of ``{tool | tools, ref}`` bindings.
    """
    if value is None:
        return None
    if isinstance(value, str) or is_ref_object(value):
        return {"by_tool": {SHARED: resolve_file_slot(value, base_path)}}
    if isinstance(value, list):
        by_tool: Dict[str, Any] = {}
        for entry in value:
            if not isinstance(entry, dict) or not isinstance(entry.get("ref"), str):
                raise TypeError("tool_fixtures list entries must be {tool | tools, ref: path}")
            payload = load_ref(entry["ref"], base_path)
            names = entry.get("tools")
            tools = [str(n) for n in names] if isinstance(names, list) and names else [str(entry.get("tool") or SHARED)]
            for name in tools:
                by_tool[name] = payload
        return {"by_tool": by_tool}
    if isinstance(value, dict) and set(value) == {"by_tool"} and isinstance(value["by_tool"], dict):
        return {"by_tool": {str(tool): _resolve_payload(spec, base_path) for tool, spec in value["by_tool"].items()}}
    keys = sorted(value) if isinstance(value, dict) else type(value).__name__
    raise ValueError(
        f"tool_fixtures: expected a path, {{ref: path}}, a binding list, or by_tool; got {keys}. "
        'Put inline payloads under by_tool (use "*" for every tool). See docs/manifests/dataset.md.'
    )
