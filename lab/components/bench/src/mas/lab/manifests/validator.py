#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""mas-lab manifest validator — two-layer validation for experiment/pipeline/lab-config YAML.

Two layers of validation are enforced in order:

  1. **Envelope JSON Schema** (raises in strict mode, warns otherwise):
     The on-disk manifest is validated against ``docs/schemas/lab/*.schema.yaml``.
     This covers experiment / pipeline / lab envelope shape only — not composed
     MAS agent fields (cardinality rules like ``design_pattern`` apply after
     resolution).

  2. **Compose → validate resolved structure** (default on):
     References are resolved, overlays stacked, defaults applied, and the
     resulting in-memory MAS dict is validated (existence, cross-refs,
     cardinality).  Bad refs or ids block composition and fail validation.
     Disabled via ``MAS_LAB_MANIFEST_RESOLVE_REFS=0`` or when no ``base_dir``
     is provided.

Usage::

    from mas.lab.manifests.validator import validate_manifest, ManifestValidationError

    validate_manifest(data, source="experiments/01/experiment.yaml", kind="experiment")
    validate_manifest(data, source="pipelines/01-plots/pipeline.yaml", kind="pipeline")
    validate_manifest(data, source="configs/lab-config.yaml", kind="lab-config")

    # Non-strict (warnings only):
    validate_manifest(data, source="...", kind="experiment", strict=False)

    # Skip ref checks:
    validate_manifest(data, source="...", kind="experiment", resolve_refs=False)

    # CLI:
    mas-lab validate experiment.yaml
    mas-lab validate pipeline.yaml --no-resolve-refs

Environment variables:
  ``MAS_LAB_MANIFEST_VALIDATE=0``      — disable all validation (tests / CI only).
  ``MAS_LAB_MANIFEST_STRICT=0``        — demote schema violations to warnings instead of errors.
                                         Default is strict-on.
  ``MAS_LAB_MANIFEST_RESOLVE_REFS=0``  — skip reference availability checks (step 2).
                                         Useful for template manifests or CI without a full repo.
"""


import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema files (JSON Schema Draft-07, YAML format)
# ---------------------------------------------------------------------------

_SCHEMA_DIR = None  # resolved lazily — see _schema_dir()


def _schema_dir() -> Path:
    global _SCHEMA_DIR
    if _SCHEMA_DIR is None:
        from mas.lab.schemas.paths import lab_schema_dir

        _SCHEMA_DIR = lab_schema_dir()
    return _SCHEMA_DIR

#: Maps the ``kind`` parameter to the corresponding ``.schema.yaml`` file.
_KIND_SCHEMA: Dict[str, str] = {
    "experiment":  "experiment.schema.yaml",
    "pipeline":    "pipeline.schema.yaml",
    "lab-config":  "lab-config.schema.yaml",
    "lab":         "lab.schema.yaml",
    "dataset":     "dataset.schema.yaml",
}

# ---------------------------------------------------------------------------
# Environment-variable gates
# ---------------------------------------------------------------------------

_DISABLED = os.environ.get("MAS_LAB_MANIFEST_VALIDATE", "1").strip() in ("0", "false", "no")
_STRICT_MODE = os.environ.get("MAS_LAB_MANIFEST_STRICT", "1").strip() not in ("0", "false", "no")
_RESOLVE_REFS = os.environ.get("MAS_LAB_MANIFEST_RESOLVE_REFS", "1").strip() not in ("0", "false", "no")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ManifestValidationError(ValueError):
    """Raised when a mas-lab manifest fails validation in strict mode."""

    def __init__(self, source: str, violations: List[str]) -> None:
        self.source = source
        self.violations = violations
        lines = "\n  ".join(violations)
        super().__init__(f"Manifest validation failed for '{source}':\n  {lines}")


# ---------------------------------------------------------------------------
# Kind auto-detection
# ---------------------------------------------------------------------------


def detect_kind(data: Dict[str, Any]) -> Optional[str]:
    """Return the manifest kind detected from the top-level key.

    Returns ``"experiment"``, ``"pipeline"``, ``"lab"``, ``"lab-config"``, or ``"dataset"``;
    or ``None`` when the document does not match any known shape.
    """
    if "experiment" in data:
        return "experiment"
    if "pipeline" in data:
        return "pipeline"
    if "lab" in data:
        lab = data.get("lab") or {}
        if isinstance(lab, dict) and any(
            k in lab for k in ("mas", "scenarios", "ui", "dataset", "evaluation")
        ):
            return "lab-config"
        return "lab"
    if data.get("kind") == "Dataset" and data.get("apiVersion") == "lab/v1":
        return "dataset"
    return None


# ---------------------------------------------------------------------------
# Step 1 — JSON Schema validation
# ---------------------------------------------------------------------------


def _validate_against_schema(data: Dict[str, Any], kind: str) -> List[str]:
    """Validate *data* against the JSON Schema for *kind*.

    Returns a list of human-readable violation strings (empty → valid).
    """
    schema_file = _schema_dir() / _KIND_SCHEMA.get(kind, "")
    if not schema_file.exists():
        logger.warning("[manifest][%s] schema file not found: %s — skipping schema validation", kind, schema_file)
        return []

    with schema_file.open(encoding="utf-8") as fh:
        schema = yaml.safe_load(fh)

    validator = jsonschema.Draft7Validator(schema)
    violations: List[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = " → ".join(str(p) for p in error.absolute_path) or "(root)"
        violations.append(f"{path}: {error.message}")
    return violations


# ---------------------------------------------------------------------------
# Step 2 — Reference availability
# ---------------------------------------------------------------------------


def _check_refs(data: Dict[str, Any], kind: str, base_dir: Path) -> List[str]:
    """Resolve references and composed MAS; return violation messages."""
    from mas.lab.manifests.ref_checks import check_lab_manifest_refs

    if not base_dir.is_dir():
        return []

    if kind == "experiment":
        payload = data.get("experiment", data)
    elif kind == "pipeline":
        payload = data.get("pipeline", data)
    elif kind in ("lab-config", "lab"):
        payload = data.get("lab", data)
    else:
        return {}

    return check_lab_manifest_refs(payload, base_dir, source=str(base_dir), kind=kind)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_manifest(
    data: Dict[str, Any],
    source: str,
    kind: Optional[str] = None,
    *,
    strict: bool = True,
    base_dir: Optional[Path] = None,
    resolve_refs: Optional[bool] = None,
) -> None:
    """Validate a mas-lab manifest dict.

    Parameters
    ----------
    data:
        Parsed YAML content (output of ``yaml.safe_load()``).
    source:
        File path or label used in error/warning messages.
    kind:
        ``"experiment"``, ``"pipeline"``, or ``"lab-config"``.
        When ``None``, auto-detected from the top-level key.
    strict:
        When ``True`` (default), violations raise :class:`ManifestValidationError`.
        When ``False``, violations are logged as warnings.  Combined with the
        ``MAS_LAB_MANIFEST_STRICT`` env var — if either is ``False``, non-strict
        mode applies.
    base_dir:
        Base directory for resolving relative paths in reference checks.
        When ``None``, derived from ``source`` if it is an existing file path.
    resolve_refs:
        Override the ``MAS_LAB_MANIFEST_RESOLVE_REFS`` env var for this call.
        ``None`` means "use the env var default".

    Raises
    ------
    ManifestValidationError
        When *strict* is ``True`` and violations are found.
    """
    if _DISABLED:
        return

    # Auto-detect kind
    if kind is None:
        kind = detect_kind(data)
    if kind is None:
        msg = f"Cannot detect manifest kind from top-level keys in '{source}'. Expected one of: experiment, pipeline, lab."
        if strict and _STRICT_MODE:
            raise ManifestValidationError(source, [msg])
        logger.warning("[manifest] %s", msg)
        return

    effective_strict = strict and _STRICT_MODE

    # Resolve base_dir from source path when not given explicitly
    _base_dir: Optional[Path] = base_dir
    if _base_dir is None and source:
        candidate = Path(source)
        if candidate.is_file():
            _base_dir = candidate.parent

    _do_resolve = _RESOLVE_REFS if resolve_refs is None else resolve_refs

    # ── Step 1: JSON Schema ────────────────────────────────────────────────
    schema_violations = _validate_against_schema(data, kind)
    if schema_violations:
        if effective_strict:
            raise ManifestValidationError(source, schema_violations)
        for msg in schema_violations:
            logger.warning("[manifest][%s] %s: %s", kind, source, msg)

    # ── Step 2: Compose + validate resolved MAS (default on) ───────────────
    if _do_resolve and _base_dir is not None:
        ref_violations = _check_refs(data, kind, _base_dir)
        if ref_violations:
            if effective_strict:
                raise ManifestValidationError(source, ref_violations)
            for msg in ref_violations:
                logger.warning("[manifest][%s] %s: %s", kind, source, msg)
