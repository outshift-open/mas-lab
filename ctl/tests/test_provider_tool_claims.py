#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Verification: ``tools: "*"`` always passes; explicit local lists are checked."""

from __future__ import annotations

from mas.ctl.validate.validator import validate_data


def _agent(**spec):
    return {
        "apiVersion": "mas/v1",
        "kind": "Agent",
        "metadata": {"name": "t"},
        "spec": {"description": "t", **spec},
    }


def test_star_mcp_provider_always_passes_validate():
    result = validate_data(
        _agent(
            providers=[
                {
                    "name": "mcp",
                    "kind": "mcp",
                    "url": "http://127.0.0.1:9001/mcp",
                    "tools": "*",
                }
            ]
        ),
        kind="agent",
        resolve_refs=False,
    )
    assert result.ok, result.issues


def test_star_local_provider_always_passes_validate():
    result = validate_data(
        _agent(providers=[{"name": "in-process", "kind": "local", "tools": "*"}]),
        kind="agent",
        resolve_refs=False,
    )
    assert result.ok, result.issues


def test_explicit_local_unknown_name_fails_validate():
    result = validate_data(
        _agent(
            tools=["calc"],
            providers=[{"name": "in-process", "kind": "local", "tools": ["no-such-tool"]}],
        ),
        kind="agent",
        resolve_refs=False,
    )
    assert not result.ok
    messages = [i.message for i in result.issues if i.level == "error"]
    assert any("no-such-tool" in m for m in messages)


def test_explicit_local_known_name_passes_validate():
    result = validate_data(
        _agent(
            tools=["calc"],
            providers=[{"name": "in-process", "kind": "local", "tools": ["calc"]}],
        ),
        kind="agent",
        resolve_refs=False,
    )
    assert result.ok, result.issues


def test_explicit_mcp_unknown_name_fails_validate():
    result = validate_data(
        _agent(
            tools=["web-search"],
            providers=[
                {
                    "name": "mcp",
                    "kind": "mcp",
                    "url": "http://127.0.0.1:9001/mcp",
                    "tools": ["no-such-tool"],
                }
            ],
        ),
        kind="agent",
        resolve_refs=False,
    )
    assert not result.ok
    messages = [i.message for i in result.issues if i.level == "error"]
    assert any("no-such-tool" in m for m in messages)


def test_explicit_mcp_known_name_passes_validate():
    result = validate_data(
        _agent(
            tools=["web-search"],
            providers=[
                {
                    "name": "mcp",
                    "kind": "mcp",
                    "url": "http://127.0.0.1:9001/mcp",
                    "tools": ["web-search"],
                }
            ],
        ),
        kind="agent",
        resolve_refs=False,
    )
    assert result.ok, result.issues


def test_overlay_explicit_local_checked_against_patch_tools():
    overlay = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "t"},
        "spec": {
            "target": {"kind": "Agent"},
            "patch": {
                "tools": ["calc"],
                "providers": [{"name": "in-process", "kind": "local", "tools": ["no-such-tool"]}],
            },
        },
    }
    result = validate_data(overlay, kind="overlay", resolve_refs=False)
    assert not result.ok
    messages = [i.message for i in result.issues if i.level == "error"]
    assert any("no-such-tool" in m for m in messages)


def test_overlay_providers_only_skips_catalogue_check():
    overlay = {
        "apiVersion": "mas/v1",
        "kind": "Overlay",
        "metadata": {"name": "t"},
        "spec": {
            "target": {"kind": "Agent"},
            "patch": {
                "providers": [
                    {
                        "name": "mcp",
                        "kind": "mcp",
                        "url": "http://127.0.0.1:9001/mcp",
                        "tools": ["web-search"],
                    }
                ]
            },
        },
    }
    result = validate_data(overlay, kind="overlay", resolve_refs=False)
    assert result.ok, result.issues


def test_explicit_local_system_tool_passes_validate():
    result = validate_data(
        _agent(
            providers=[{"name": "in-process", "kind": "local", "tools": ["request_human_input"]}],
        ),
        kind="agent",
        resolve_refs=False,
    )
    assert result.ok, result.issues
