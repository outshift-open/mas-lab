#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""In-process manifest validation for controller HTTP routes (no CLI subprocess)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mas.ctl.validate.schemas import declared_kind, schema_path_for_kind
from mas.ctl.validate.validator import validate_data


def validate_manifest_yaml_content(
    manifest_yaml: str,
    *,
    base_dir: Path,
    kind: str | None = None,
    resolve_refs: bool = True,
) -> dict[str, Any]:
    """Validate inline YAML; return legacy CLI-shaped dict for API compatibility."""
    try:
        data = yaml.safe_load(manifest_yaml)
    except yaml.YAMLError as exc:
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": f"YAML parse error: {exc}",
            "command": "validate_data",
            "valid": False,
        }

    if not isinstance(data, dict):
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": "manifest must be a YAML mapping",
            "command": "validate_data",
            "valid": False,
        }

    resolved_kind = kind or declared_kind(data)
    if resolved_kind is None or schema_path_for_kind(resolved_kind) is None:
        return {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "command": "validate_data",
            "valid": True,
        }

    result = validate_data(
        data,
        source="<inline>",
        kind=resolved_kind,
        base_dir=base_dir,
        resolve_refs=resolve_refs,
    )

    errors = [i for i in result.issues if i.level == "error"]
    warnings = [i for i in result.issues if i.level == "warning"]
    lines = [f"[{i.level}] {i.message}" for i in errors + warnings]
    stderr = "\n".join(lines)

    return {
        "exit_code": 0 if result.ok else 1,
        "stdout": "",
        "stderr": stderr,
        "command": "validate_data",
        "valid": result.ok,
        "issues": [{"level": i.level, "message": i.message, "path": i.path} for i in result.issues],
    }


def validate_overlay_yaml_content(content: str, *, base_dir: Path) -> list[str] | None:
    """Validate overlay YAML; return error strings or None when valid."""
    outcome = validate_manifest_yaml_content(
        content,
        base_dir=base_dir,
        kind="overlay",
        resolve_refs=False,
    )
    if outcome.get("valid"):
        return None
    stderr = str(outcome.get("stderr") or "").strip()
    if stderr:
        return [line.strip() for line in stderr.splitlines() if line.strip()]
    return ["Validation failed"]
