#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Overlay-agent-patch schema unification: fields $ref straight into
agent.schema.yaml instead of re-declaring their shape (see
docs/schemas/runtime/fragments/overlay-agent-patch.schema.yaml)."""

from __future__ import annotations

from pathlib import Path

import yaml
from mas.ctl.validate import validate_file


def _write(tmp_path: Path, patch: dict) -> Path:
    p = tmp_path / "overlay.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "kind": "Overlay",
                "apiVersion": "mas/v1",
                "metadata": {"name": "t"},
                "spec": {"target": {"kind": "Agent"}, "patch": patch},
            }
        ),
        encoding="utf-8",
    )
    return p


def test_working_memory_persistent_patch_validates(tmp_path: Path):
    result = validate_file(_write(tmp_path, {"working_memory": {"persistent": True}}), kind="overlay")
    assert result.ok, result.issues


def test_working_memory_unknown_nested_field_is_rejected(tmp_path: Path):
    result = validate_file(_write(tmp_path, {"working_memory": {"persistent": True, "bogus": 1}}), kind="overlay")
    assert not result.ok


def test_params_patch_validates(tmp_path: Path):
    """params had no base-schema declaration until this fix -- now real."""
    result = validate_file(_write(tmp_path, {"params": {"foo": "bar"}}), kind="overlay")
    assert result.ok, result.issues


def test_memory_object_form_now_validates_not_just_string_shorthand(tmp_path: Path):
    """memory's overlay-patch shape used to be string-only; $ref-ing straight
    into the base schema's full oneOf widens it to accept the object form
    too -- a deliberate, backward-compatible widening."""
    result = validate_file(_write(tmp_path, {"memory": {"enabled": True}}), kind="overlay")
    assert result.ok, result.issues
    result_string = validate_file(_write(tmp_path, {"memory": "semantic"}), kind="overlay")
    assert result_string.ok, result_string.issues


def test_context_policy_is_rejected_as_dead_field(tmp_path: Path):
    """context_policy had zero consumers anywhere in the repo -- removed."""
    result = validate_file(_write(tmp_path, {"context_policy": {"foo": "bar"}}), kind="overlay")
    assert not result.ok


def test_tools_op_remove_wrapper_still_validates(tmp_path: Path):
    """Ops-wrapped fields (list_ops/plugin_list_ops) keep their own dedicated
    fragment -- their overlay-patch shape genuinely differs from the base
    schema's (accepts {"$op": {...}}), so it's not $ref-into-base. tools'
    own {"$op": {"remove": [...]}} is what tools_remove (a separate,
    now-removed attribute) used to duplicate."""
    result = validate_file(_write(tmp_path, {"tools": {"$op": {"remove": ["calculator"]}}}), kind="overlay")
    assert result.ok, result.issues


def test_providers_mcp_patch_validates(tmp_path: Path):
    result = validate_file(
        _write(
            tmp_path,
            {
                "providers": [
                    {
                        "name": "localhost-mcp-tools",
                        "kind": "mcp",
                        "transport": "streamable-http",
                        "url": "http://127.0.0.1:9001/mcp",
                        "tools": "*",
                    }
                ]
            },
        ),
        kind="overlay",
    )
    assert result.ok, result.issues


def test_samples_mcp_localhost_overlay_validates():
    path = Path(__file__).resolve().parents[2] / "library-samples/overlays/mcp-localhost.yaml"
    result = validate_file(path, kind="overlay")
    assert result.ok, result.issues


def test_samples_local_in_process_overlay_validates():
    path = Path(__file__).resolve().parents[2] / "library-samples/overlays/local-in-process.yaml"
    result = validate_file(path, kind="overlay")
    assert result.ok, result.issues


def test_tools_remove_is_rejected_as_a_removed_field(tmp_path: Path):
    result = validate_file(_write(tmp_path, {"tools_remove": ["calculator"]}), kind="overlay")
    assert not result.ok


def test_explicit_mcp_tools_list_validates_without_a_server(tmp_path: Path):
    """Star and explicit MCP lists both pass overlay validate — no live query."""
    result = validate_file(
        _write(
            tmp_path,
            {
                "providers": [
                    {
                        "name": "localhost-mcp-tools",
                        "kind": "mcp",
                        "transport": "streamable-http",
                        "url": "http://127.0.0.1:9001/mcp",
                        "tools": ["web-search"],
                    }
                ]
            },
        ),
        kind="overlay",
    )
    assert result.ok, result.issues
