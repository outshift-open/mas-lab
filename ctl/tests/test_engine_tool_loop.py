#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tool egress is structural (spec.tools + pattern), not a governance boolean."""

from __future__ import annotations

from mas.ctl.session.manifest_config import engine_use_tool_loop, kernel_config_from_manifest


def test_declared_tools_enable_llm_tool_catalog():
    manifest = {
        "spec": {
            "tools": ["web-search", "calculator"],
        }
    }
    kernel = kernel_config_from_manifest(manifest)
    assert engine_use_tool_loop(manifest, kernel) is True


def test_no_tools_means_no_llm_tool_catalog():
    manifest = {"spec": {"context": {"role": "helper"}}}
    kernel = kernel_config_from_manifest(manifest)
    assert engine_use_tool_loop(manifest, kernel) is False


def test_plan_execute_pattern_uses_dp_tool_scheduling():
    manifest = {"spec": {"tools": ["calculator"]}}
    kernel = kernel_config_from_manifest(manifest, pattern_plugin_id="plan_execute@v1")
    assert engine_use_tool_loop(manifest, kernel) is False
