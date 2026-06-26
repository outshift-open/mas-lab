#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""JSON Schema validation helpers for pipeline steps and artifacts.

The benchmark pipeline accepts schema specs either inline (dict) or as a file
path (JSON/YAML). These helpers centralize schema loading and payload
validation so executor, steps, and artifacts all use the same behavior.
"""


import json
from pathlib import Path
from typing import Any, Optional

import yaml
from jsonschema import Draft7Validator


def resolve_schema(schema_spec: Any, *, base_dir: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Resolve a schema specification into a JSON-schema dict.

    Args:
        schema_spec: Either:
            - ``None``: no validation,
            - ``dict``: inline schema,
            - ``str``: path to a ``.json``, ``.yaml`` or ``.yml`` schema file.
        base_dir: Base directory used to resolve relative schema paths.

    Returns:
        A schema dict, or ``None`` when *schema_spec* is ``None``.
    """
    if schema_spec is None:
        return None
    if isinstance(schema_spec, dict):
        return schema_spec
    if not isinstance(schema_spec, str):
        raise TypeError(
            f"schema spec must be None, dict, or str path, got {type(schema_spec).__name__}"
        )

    path = Path(schema_spec).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = (base_dir / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"schema file not found: {path}")

    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)

    if not isinstance(loaded, dict):
        raise ValueError(f"schema file must contain a JSON object at root: {path}")
    return loaded


def validate_payload(
    payload: Any,
    schema_spec: Any,
    *,
    label: str,
    base_dir: Optional[Path] = None,
    max_errors: int = 5,
) -> None:
    """Validate *payload* against *schema_spec*.

    No-op when *schema_spec* is ``None``.
    Raises ``ValueError`` with a compact error summary on validation failure.
    """
    schema = resolve_schema(schema_spec, base_dir=base_dir)
    if schema is None:
        return

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if not errors:
        return

    lines: list[str] = []
    for err in errors[:max_errors]:
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        lines.append(f"{path}: {err.message}")
    remaining = len(errors) - len(lines)
    if remaining > 0:
        lines.append(f"... and {remaining} more error(s)")

    raise ValueError(f"{label}: schema validation failed:\n  - " + "\n  - ".join(lines))
