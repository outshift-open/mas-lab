#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Optional ``spec.schemas``: JSON Schemas for the free-form parts of dataset items.

Keys are dotted envelope paths, the same vocabulary as ``spec.source.map``.
Only free-form roots can carry a schema; the generic layer is already covered
by ``run-input.schema.yaml``:

- ``expectations.details[.<key>...]``
- ``inputs.tool_fixtures.by_tool.<tool | *>[.<key>...]``

A tool key is checked against the payload that tool receives at run time
(``by_tool[tool]``, else ``by_tool["*"]``), matching ``tool_fixture(ctx, tool)``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from mas.lab.inputs.refs import resolve_file_slot

_DETAILS = ("expectations", "details")
_BY_TOOL = ("inputs", "tool_fixtures", "by_tool")
_MISSING = object()


def _parse_key(key: str) -> tuple[str, ...]:
    parts = tuple(key.split("."))
    if parts[:2] == _DETAILS or (parts[:3] == _BY_TOOL and len(parts) > 3 and parts[3]):
        return parts
    raise ValueError(
        f"spec.schemas: {key!r} is not a free-form part; use expectations.details[...] "
        "or inputs.tool_fixtures.by_tool.<tool>[...]"
    )


def load_part_schemas(value: Any, base_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Resolve ``spec.schemas`` to ``{dotted path: JSON Schema}``; refs load relative to the dataset."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("spec.schemas must map dotted envelope paths to schemas")
    out: Dict[str, Dict[str, Any]] = {}
    for key, spec in value.items():
        _parse_key(str(key))
        schema = resolve_file_slot(spec, base_path)
        if not isinstance(schema, dict):
            raise TypeError(f"spec.schemas.{key}: expected a JSON Schema mapping, a path, or {{ref: path}}")
        jsonschema.Draft7Validator.check_schema(schema)
        out[str(key)] = schema
    return out


def _lookup(envelope: Dict[str, Any], parts: tuple[str, ...]) -> Any:
    node: Any = envelope
    for i, part in enumerate(parts):
        if not isinstance(node, dict):
            return _MISSING
        if i == 3 and parts[:3] == _BY_TOOL and part not in node:
            part = "*"
        if part not in node:
            return _MISSING
        node = node[part]
    return node


def part_schema_violations(
    envelope: Dict[str, Any], schemas: Dict[str, Dict[str, Any]], *, where: str
) -> List[str]:
    """Check a resolved item envelope; parts the item does not provide are skipped."""
    violations: List[str] = []
    for key, schema in schemas.items():
        value = _lookup(envelope, _parse_key(key))
        if value is _MISSING:
            continue
        for err in jsonschema.Draft7Validator(schema).iter_errors(value):
            at = ".".join(str(p) for p in err.absolute_path)
            violations.append(f"{where}: {key}{'.' + at if at else ''}: {err.message}")
    return violations
