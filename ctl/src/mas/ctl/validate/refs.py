#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Reference availability — recursive filesystem refs + kind-specific cross-refs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

REF_KEYS = frozenset(
    {
        "ref",
        "manifest",
        "mas_ref",
        "configs_dir",
        "instructions_ref",
        "tools_ref",
        "workflow",
        "deployment_ref",
        "spec_overlay_ref",
        "overlay",
        "path",
    }
)

_SKIP_PREFIXES = ("bundle://", "module://", "oci://", "pkg://", "infra:", "samples:", "standard:")


def resolve_refs_enabled() -> bool:
    return os.environ.get("MAS_MANIFEST_RESOLVE_REFS", "1") not in ("0", "false", "False")


def is_path_ref(key: str, value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if any(value.startswith(p) for p in _SKIP_PREFIXES):
        return False
    if key in ("configs_dir", "path"):
        return True
    if key == "tools_ref":
        return "/" in value or "\\" in value or value.endswith((".yaml", ".yml", ".json"))
    if key == "workflow":
        return value.endswith((".yaml", ".yml", ".json")) or "/" in value or value.startswith(".")
    if key in ("ref", "mas_ref", "manifest", "overlay"):
        return (
            value.startswith("./")
            or value.startswith("../")
            or "/" in value
            or value.endswith((".yaml", ".yml", ".json", ".md", ".py"))
        )
    if key == "instructions_ref":
        return not value.startswith("bundle://")
    return key in REF_KEYS and ("/" in value or value.endswith((".yaml", ".yml")))


def iter_ref_paths(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            if k in REF_KEYS and is_path_ref(k, v):
                found.append((p, v))
            found.extend(iter_ref_paths(v, p))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, dict) and "ref" in item and isinstance(item["ref"], str):
                p = f"{prefix}[{i}].ref"
                if is_path_ref("ref", item["ref"]):
                    found.append((p, item["ref"]))
            found.extend(iter_ref_paths(item, f"{prefix}[{i}]"))
    return found


def _check_mas_workflow_ids(spec: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    workflow = spec.get("workflow")
    if not isinstance(workflow, dict):
        return violations
    nodes = workflow.get("nodes") or []
    node_ids = {n.get("id") for n in nodes if isinstance(n, dict) and n.get("id")}
    entry = workflow.get("entry")
    if entry and node_ids and entry not in node_ids:
        violations.append(
            f"spec.workflow.entry = {entry!r} — unknown node id (known: {sorted(node_ids)})"
        )
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id", f"[{i}]")
        for j, target in enumerate(node.get("delegates_to") or []):
            if node_ids and target not in node_ids:
                violations.append(
                    f"spec.workflow.nodes[{i}] ({node_id!r}).delegates_to[{j}] "
                    f"= {target!r} — unknown node id"
                )
    return violations


def _resolve_ref_target(base_dir: Path, ref: str) -> Path:
    if ref.startswith("/"):
        return Path(ref)
    direct = (base_dir / ref).resolve()
    if direct.exists():
        return direct
    # MAS topology overlays use refs relative to the MAS root, not overlays/.
    for parent in base_dir.parents:
        candidate = (parent / ref).resolve()
        if candidate.exists():
            return candidate
    return direct


def check_refs(data: dict[str, Any], kind: str | None, base_dir: Path | None) -> list[str]:
    if not kind or base_dir is None or not base_dir.is_dir():
        return []
    if not resolve_refs_enabled():
        return []

    violations: list[str] = []
    spec = data.get("spec") or {}

    # Recursive filesystem refs
    for path, ref in iter_ref_paths(data):
        target = _resolve_ref_target(base_dir, ref)
        if not target.exists():
            violations.append(f"{path} = {ref!r} — not found: {target}")

    # tools_ref must be logical name (not path) — override recursive false positive
    tools_ref = spec.get("tools_ref")
    if tools_ref and isinstance(tools_ref, str):
        if "/" in tools_ref or "\\" in tools_ref or tools_ref.endswith(".json"):
            violations.append(
                f"spec.tools_ref = {tools_ref!r} — must be a logical name, not a file path"
            )

    if kind == "mas":
        violations.extend(_check_mas_workflow_ids(spec))

    return violations
