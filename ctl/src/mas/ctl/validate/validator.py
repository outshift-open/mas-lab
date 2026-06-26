#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest validation — ctl responsibility; runtime never validates YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mas.ctl.validate.schemas import declared_kind, load_schema, schema_path_for_kind
from mas.ctl.validate.refs import check_refs, resolve_refs_enabled
from mas.ctl.validate.separation import check_separation


@dataclass
class ValidationIssue:
    level: str  # error | warning
    message: str
    path: str = ""


@dataclass
class ValidationResult:
    ok: bool
    kind: str | None = None
    source: str = ""
    issues: list[ValidationIssue] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        errors = [i for i in self.issues if i.level == "error"]
        if errors:
            lines = "\n".join(f"  [{i.level}] {i.message}" for i in errors)
            raise ValueError(f"validation failed for {self.source}:\n{lines}")


def validation_enabled() -> bool:
    return os.environ.get("MAS_MANIFEST_VALIDATE", "1") not in ("0", "false", "False")


def strict_mode() -> bool:
    return os.environ.get("MAS_MANIFEST_STRICT", "1") not in ("0", "false", "False")


def validate_data(
    data: dict[str, Any],
    *,
    source: str = "",
    kind: str | None = None,
    strict: bool | None = None,
    base_dir: Path | None = None,
    resolve_refs: bool | None = None,
) -> ValidationResult:
    """Validate manifest dict against JSON Schema Draft-07 + separation + refs."""
    if strict is None:
        strict = strict_mode()
    resolved_kind = kind or declared_kind(data)
    result = ValidationResult(ok=True, kind=resolved_kind, source=source)

    if resolved_kind is None:
        result.issues.append(
            ValidationIssue("error", "manifest missing kind (expected explicit kind or lab envelope key)")
        )
        result.ok = False
        return result

    if schema_path_for_kind(resolved_kind) is None:
        result.issues.append(
            ValidationIssue("warning", f"no schema file for kind {resolved_kind!r}")
        )
        return result

    try:
        import jsonschema
    except ImportError as exc:
        result.issues.append(ValidationIssue("error", f"jsonschema required: {exc}"))
        result.ok = False
        return result

    schema = load_schema(resolved_kind)
    validator = jsonschema.Draft7Validator(schema)
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.path) or "(root)"
        level = "error" if strict else "warning"
        result.issues.append(ValidationIssue(level, err.message, path=path))

    if any(i.level == "error" for i in result.issues):
        result.ok = False

    if resolved_kind == "agent":
        try:
            from mas.ctl.manifest.spec_bindings import validate_agent_spec_bindings

            validate_agent_spec_bindings(data.get("spec"))
        except Exception as exc:
            result.issues.append(
                ValidationIssue("error", str(exc), path="spec")
            )
            result.ok = False

    if resolved_kind == "deployment":
        spec = data.get("spec") or {}
        runtime_id = spec.get("runtime_id")
        if runtime_id:
            try:
                from mas.ctl.registry.catalog import validate_runtime_id

                validate_runtime_id(str(runtime_id))
            except KeyError as exc:
                result.issues.append(
                    ValidationIssue("error", str(exc), path="spec.runtime_id")
                )
                result.ok = False

    for msg in check_separation(data, resolved_kind):
        result.issues.append(ValidationIssue("error" if strict else "warning", msg))
    if strict and any(i.level == "error" for i in result.issues):
        result.ok = False

    do_refs = resolve_refs if resolve_refs is not None else resolve_refs_enabled()
    if do_refs:
        ref_base = base_dir
        if ref_base is None and source:
            ref_base = Path(source).parent
        for msg in check_refs(data, resolved_kind, ref_base):
            result.issues.append(ValidationIssue("error" if strict else "warning", msg))

    if any(i.level == "error" for i in result.issues):
        result.ok = False
    return result


def validate_file(
    path: Path,
    *,
    kind: str | None = None,
    strict: bool | None = None,
    resolve_refs: bool | None = None,
) -> ValidationResult:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return ValidationResult(
            ok=False,
            source=str(path),
            issues=[ValidationIssue("error", "manifest must be a YAML mapping")],
        )
    return validate_data(
        raw,
        source=str(path),
        kind=kind,
        strict=strict,
        base_dir=path.parent,
        resolve_refs=resolve_refs,
    )


def validate_tree(
    root: Path,
    *,
    strict: bool | None = None,
    resolve_refs: bool | None = None,
) -> list[ValidationResult]:
    """Validate all *.yaml under root."""
    results: list[ValidationResult] = []
    for path in sorted(root.rglob("*.yaml")):
        if path.name.startswith("."):
            continue
        results.append(validate_file(path, strict=strict, resolve_refs=resolve_refs))
    return results
