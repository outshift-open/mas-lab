#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Human-readable JSON Schema validation messages."""

from __future__ import annotations

import re
from typing import Any

from mas.ctl.validate.deprecations import hint_for_removed_experiment_key

_UNKNOWN_PROPERTY_RE = re.compile(
    r"^(?P<fields>(?:'[^']+'(?:,\s*)?)+)\s+do not match any of the regexes:\s+'\^x-'",
    re.MULTILINE,
)
_UNKNOWN_PROPERTY_SINGLE_RE = re.compile(
    r"^'(?P<field>[^']+)'\s+does not match any of the regexes:\s+'\^x-'"
)
_ADDITIONAL_PROPERTY_RE = re.compile(
    r"^Additional properties are not allowed \('(?P<field>[^']+)' was unexpected\)$"
)
_ADDITIONAL_PROPERTIES_MULTI_RE = re.compile(
    r"^Additional properties are not allowed \((?P<fields>(?:'[^']+'(?:,\s*)?)+) were unexpected\)$"
)
_REQUIRED_RE = re.compile(r"^'(?P<field>[^']+)' is a required property$")


def _field_path(path: str, field: str) -> str:
    if not path or path == "(root)":
        return field
    return f"{path}.{field}"


def _removed_hint(field: str) -> str:
    return hint_for_removed_experiment_key(field)


def humanize_schema_error(err: Any) -> str:
    """Translate jsonschema defaults into plain invalid-field messages."""
    message = str(getattr(err, "message", err) or "")
    path = ".".join(str(p) for p in getattr(err, "path", ()) or ()) or "(root)"

    m = _UNKNOWN_PROPERTY_SINGLE_RE.match(message)
    if m:
        return f"{_field_path(path, m.group('field'))} is not a valid property"

    m = _UNKNOWN_PROPERTY_RE.match(message)
    if m:
        fields = re.findall(r"'([^']+)'", m.group("fields"))
        if len(fields) == 1:
            return f"{_field_path(path, fields[0])} is not a valid property"
        joined = ", ".join(_field_path(path, name) for name in fields)
        return f"{joined} are not valid properties"

    m = _ADDITIONAL_PROPERTY_RE.match(message)
    if m:
        field = m.group("field")
        msg = f"{_field_path(path, field)} is not a valid property"
        extra = _removed_hint(field)
        return f"{msg} ({extra})" if extra else msg

    m = _ADDITIONAL_PROPERTIES_MULTI_RE.match(message)
    if m:
        fields = re.findall(r"'([^']+)'", m.group("fields"))
        if len(fields) == 1:
            msg = f"{_field_path(path, fields[0])} is not a valid property"
            extra = _removed_hint(fields[0])
            return f"{msg} ({extra})" if extra else msg
        joined = ", ".join(_field_path(path, name) for name in fields)
        return f"{joined} are not valid properties"

    m = _REQUIRED_RE.match(message)
    if m:
        return f"{_field_path(path, m.group('field'))} is required"

    return message
