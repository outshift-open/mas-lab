#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for human-readable JSON Schema validation messages."""

from __future__ import annotations

from mas.ctl.validate.schema_errors import humanize_schema_error
from mas.ctl.validate.validator import _path_sort_key, validate_data


def test_humanize_unknown_spec_fields_not_regex_message() -> None:
    result = validate_data(
        {
            "apiVersion": "mas/v1",
            "kind": "Agent",
            "metadata": {"name": "test"},
            "spec": {
                "description": "test agent",
                "role": "old",
                "intent": "old intent",
            },
        },
        kind="agent",
        resolve_refs=False,
    )
    assert not result.ok
    messages = [i.message for i in result.issues if i.level == "error"]
    assert any("spec.intent, spec.role are not valid properties" in m for m in messages)
    assert not any("regex" in m.lower() for m in messages)


def test_humanize_single_unknown_field() -> None:
    result = validate_data(
        {
            "apiVersion": "mas/v1",
            "kind": "Agent",
            "metadata": {"name": "test"},
            "spec": {
                "description": "test agent",
                "system_prompt": "legacy",
            },
        },
        kind="agent",
        resolve_refs=False,
    )
    assert not result.ok
    messages = [i.message for i in result.issues if i.level == "error"]
    assert any("spec.system_prompt is not a valid property" in m for m in messages)


def test_humanize_required_property() -> None:
    class _Err:
        message = "'description' is a required property"
        path = ("spec",)

    assert humanize_schema_error(_Err()) == "spec.description is required"


def test_path_sort_key_handles_mixed_int_and_string_segments() -> None:
    mixed_paths = [
        ("spec", "tools", "0"),
        ("spec", "tools", 0),
        ("spec", "tools", 1),
        ("spec", "tools", "name"),
    ]

    ordered = sorted(mixed_paths, key=_path_sort_key)
    assert ordered == [
        ("spec", "tools", "0"),
        ("spec", "tools", "name"),
        ("spec", "tools", 0),
        ("spec", "tools", 1),
    ]
