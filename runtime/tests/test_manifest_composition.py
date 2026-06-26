#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for manifest composition helpers."""

from mas.ctl.overlay import apply_merge_patch, merge_agent_overlay


def test_apply_merge_patch_deletes_keys_with_none() -> None:
    target = {"spec": {"telemetry": {"path": "a.jsonl", "backend": "otel"}}}
    patch = {"spec": {"telemetry": {"backend": None}}}

    result = apply_merge_patch(target, patch)

    assert result == {"spec": {"telemetry": {"path": "a.jsonl"}}}


def test_merge_agent_overlay_appends_unique_tools_remove() -> None:
    base = {"spec": {"tools_remove": ["calc"]}}
    overlay = {"spec": {"tools_remove": ["calc", "query_graph_database"]}}

    result = merge_agent_overlay(base, overlay)

    assert result["spec"]["tools_remove"] == ["calc", "query_graph_database"]


def test_merge_agent_overlay_overrides_plugins_by_name() -> None:
    base = {"spec": {"plugins": [{"name": "obs", "enabled": True}, {"name": "skills", "enabled": True}]}}
    overlay = {"spec": {"plugins": [{"name": "obs", "enabled": False}]}}

    result = merge_agent_overlay(base, overlay)

    assert result["spec"]["plugins"] == [
        {"name": "obs", "enabled": False},
        {"name": "skills", "enabled": True},
    ]