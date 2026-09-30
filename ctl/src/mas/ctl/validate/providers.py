#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Provider tool-claim checks for ``mas-ctl validate``.

``tools: "*"`` always passes — presence is filled at runtime initialization.

An explicit ``tools: [name, …]`` list is checked against ``spec.tools`` (and
runtime system tools) when those names are known. That includes ``kind: mcp``:
validate does not query a live server; it checks the claim against the agent
catalogue. Runtime init still verifies the provider actually advertises them.

Overlay-only files are checked against ``spec.patch.tools`` when that patch
declares tools. Overlay-only files that only patch ``providers`` are checked
after merge onto the agent (``mas-ctl validate agent.yaml -o overlay.yaml``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from mas.runtime.engine.tool_routing import SYSTEM_TOOL_NAMES, is_star_claim


def _is_star_tools(tools: Any) -> bool:
    if tools is None:
        return True
    if is_star_claim(tools):
        return True
    if isinstance(tools, list) and len(tools) == 1 and tools[0] == "*":
        return True
    return False


def _providers(data: dict[str, Any], kind: str | None) -> list[tuple[str, dict[str, Any]]]:
    spec = data.get("spec") if isinstance(data.get("spec"), dict) else {}
    entries: list[tuple[str, dict[str, Any]]] = []
    if kind == "overlay":
        patch = spec.get("patch") if isinstance(spec.get("patch"), dict) else {}
        raw = patch.get("providers") or []
        prefix = "spec.patch.providers"
    else:
        raw = list(spec.get("providers") or [])
        if not raw:
            raw = list(data.get("providers") or [])
        prefix = "spec.providers"
    for i, item in enumerate(raw):
        if isinstance(item, dict):
            entries.append((f"{prefix}[{i}]", item))
    return entries


def _resolve_tool_yaml(base_dir: Path | None, ref: str) -> Path | None:
    if base_dir is None or not ref:
        return None
    scheme, sep, _ = ref.partition(":")
    if sep and scheme and "/" not in scheme and "\\" not in scheme and not ref.startswith(("./", "../")):
        return None
    path = Path(ref)
    if path.is_absolute():
        return path if path.exists() else None
    direct = (base_dir / ref).resolve()
    if direct.exists():
        return direct
    for parent in base_dir.parents:
        candidate = (parent / ref).resolve()
        if candidate.exists():
            return candidate
    return None


def spec_tool_names(spec: dict[str, Any], base_dir: Path | None) -> set[str]:
    """Names verification can see without starting providers."""
    names = set(SYSTEM_TOOL_NAMES)
    for entry in spec.get("tools") or []:
        if isinstance(entry, str) and entry:
            names.add(entry)
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("name"):
            names.add(str(entry["name"]))
        ref = entry.get("ref")
        if not isinstance(ref, str) or not ref:
            continue
        path = _resolve_tool_yaml(base_dir, ref)
        if path is None:
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        md_name = (doc.get("metadata") or {}).get("name") if isinstance(doc.get("metadata"), dict) else None
        if md_name:
            names.add(str(md_name))
    return names


def check_provider_tool_claims(
    data: dict[str, Any],
    kind: str | None,
    base_dir: Path | None,
) -> list[str]:
    """Return verification errors for explicit claims. Star claims pass."""
    if kind not in {"agent", "overlay"}:
        return []
    violations: list[str] = []
    spec = data.get("spec") if isinstance(data.get("spec"), dict) else {}
    if kind == "overlay":
        patch = spec.get("patch") if isinstance(spec.get("patch"), dict) else {}
        known = spec_tool_names(patch, base_dir) if patch.get("tools") else None
    else:
        known = spec_tool_names(spec, base_dir)
    for path, provider in _providers(data, kind):
        tools = provider.get("tools", "*")
        if _is_star_tools(tools):
            continue
        names = [str(n) for n in tools] if isinstance(tools, list) else [str(tools)]
        names = [n for n in names if n and n != "*"]
        if known is None:
            continue
        missing = [n for n in names if n not in known]
        if missing:
            listed = ", ".join(repr(n) for n in missing)
            violations.append(
                f"{path}.tools claims {listed} but those names are not in spec.tools "
                "(or system tools). Use tools: '*' to defer presence to runtime initialization."
            )
    return violations
