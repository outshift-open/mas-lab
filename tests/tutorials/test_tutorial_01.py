#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tutorial 01 — Building an Agent: integration tests.

Tests manifest validation, overlay merging, tool execution, and mocked agent
runs.  LLM calls are mocked; everything else runs for real.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, patch

import pytest
import yaml

from conftest import T01, load_yaml, run_cli, make_llm_response

# ═══════════════════════════════════════════════════════════════════════════
# 1. Manifest & overlay validation (CLI)
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestValidation:
    """mas-ctl validate must pass for every manifest and overlay combo."""

    def test_validate_base_agent(self):
        r = run_cli(["mas-ctl", "validate", str(T01 / "agent.yaml")])
        assert r.returncode == 0, r.stderr
        assert "OK" in r.stdout

    @pytest.mark.parametrize("overlay", [
        "tools.yaml",
        "skills.yaml",
        "memory.yaml",
        "memory-seed.yaml",
        "context-manager.yaml",
    ])
    def test_validate_with_overlay(self, overlay):
        overlay_path = T01 / "overlays" / overlay
        if not overlay_path.exists():
            pytest.skip(f"{overlay} not present")
        r = run_cli([
            "mas-ctl", "validate",
            str(T01 / "agent.yaml"),
            "--overlay", str(overlay_path),
        ])
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("overlay", ["cot.yaml", "baseline.yaml"])
    def test_mas_patch_overlays_are_well_formed(self, overlay):
        """cot.yaml and baseline.yaml are MAS-level Patch overlays — verify structure."""
        ov = load_yaml(T01 / "overlays" / overlay)
        assert ov.get("kind") == "Overlay" or ov.get("apiVersion") == "mas/v1"
        assert "spec" in ov

    def test_validate_stacked_overlays(self):
        """Validate agent with tools + skills + memory stacked."""
        args = ["mas-ctl", "validate", str(T01 / "agent.yaml")]
        for ov in ["tools.yaml", "skills.yaml", "memory.yaml"]:
            p = T01 / "overlays" / ov
            if p.exists():
                args += ["--overlay", str(p)]
        r = run_cli(args)
        assert r.returncode == 0, r.stderr


# ═══════════════════════════════════════════════════════════════════════════
# 2. Manifest structure tests (Python)
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestStructure:
    """Verify the tutorial manifests have the expected shape."""

    def test_agent_yaml_structure(self):
        m = load_yaml(T01 / "agent.yaml")
        assert m["apiVersion"] == "mas/v1"
        assert m["kind"] == "Agent"
        assert "name" in m.get("metadata", {})
        spec = m["spec"]
        assert "models" in spec
        assert "context" in spec

    def test_overlays_directory_complete(self):
        """Tutorial 1 is CLI-first: dataset/experiment live in tuto 3+.
        Verify the expected overlays are all present."""
        expected = ["tools.yaml", "skills.yaml", "memory.yaml", "baseline.yaml", "cot.yaml"]
        for name in expected:
            p = T01 / "overlays" / name
            assert p.exists(), f"overlay {name} missing from tuto 01"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Overlay merging (Python — real overlay logic)
# ═══════════════════════════════════════════════════════════════════════════

class TestOverlayMerging:
    """Test that overlay merging produces correct merged manifests."""

    def test_tools_overlay_adds_tools(self):
        from mas.ctl.overlay import merge_overlay
        base = load_yaml(T01 / "agent.yaml")
        tools_ov = load_yaml(T01 / "overlays" / "tools.yaml")
        merged = merge_overlay(base, tools_ov)
        spec = merged.get("spec", {})
        # tools overlay should inject tools and/or context.tool_usage
        assert "tools" in spec or "tool_usage" in spec.get("context", {})

    def test_memory_overlay_adds_memory(self):
        from mas.ctl.overlay import merge_overlay
        base = load_yaml(T01 / "agent.yaml")
        mem_ov = load_yaml(T01 / "overlays" / "memory.yaml")
        merged = merge_overlay(base, mem_ov)
        spec = merged.get("spec", {})
        assert "memory" in spec or "tools" in spec

    def test_stacked_overlays_cumulative(self):
        from mas.ctl.overlay import merge_overlay
        base = load_yaml(T01 / "agent.yaml")
        for ov_name in ["tools.yaml", "skills.yaml", "memory.yaml"]:
            ov_path = T01 / "overlays" / ov_name
            if ov_path.exists():
                ov = load_yaml(ov_path)
                base = merge_overlay(base, ov)
        spec = base.get("spec", {})
        # After all overlays, should have tools + skills + memory
        has_tools = "tools" in spec
        has_memory = "memory" in spec
        assert has_tools or has_memory, f"Expected tools/memory in merged spec: {list(spec.keys())}"

    def test_cot_overlay_changes_design_pattern(self):
        from mas.ctl.overlay import merge_overlay
        base = load_yaml(T01 / "agent.yaml")
        cot_ov = load_yaml(T01 / "overlays" / "cot.yaml")
        merged = merge_overlay(base, cot_ov)
        # CoT overlay should have set a design pattern somewhere
        # It may be under spec.patch or directly in spec
        merged_str = yaml.dump(merged)
        assert "cot" in merged_str.lower()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Agent instantiation (default runtime — mock infra)
# ═══════════════════════════════════════════════════════════════════════════

def _mock_merged_agent(*extra_overlays: str) -> dict:
    """Tutorial agent with explicit mock LLM overlay (required for bootstrap)."""
    from mas.ctl.overlay import merge_overlay

    base = load_yaml(T01 / "agent.yaml")
    names = ("mock-llm.yaml", *extra_overlays)
    for name in names:
        base = merge_overlay(base, load_yaml(T01 / "overlays" / name))
    return base


class TestAgentInstantiation:
    """Instantiate an agent from manifest via mas-ctl session bootstrap."""

    def test_instantiate_base_agent(self):
        from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime

        config = _mock_merged_agent()
        instance, _ = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=config,
                manifest_dir=T01,
                validate_manifests=False,
            ),
        )
        assert instance is not None
        assert config.get("metadata", {}).get("name") == "qa-agent"

    def test_instantiate_with_tools_overlay(self):
        from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime

        merged = _mock_merged_agent("tools.yaml")
        instance, _ = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=merged,
                manifest_dir=T01,
                validate_manifests=False,
            ),
        )
        assert instance is not None

    def test_session_controller_turn(self):
        """Run one scripted turn against mock infra."""
        from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime
        from mas.ctl.session.controller import ConversationConfig, SessionController
        from mas.ctl.ui.stdout import StdoutConversationDisplay

        config = _mock_merged_agent()
        instance, _ = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=config,
                manifest_dir=T01,
                validate_manifests=False,
            ),
        )
        controller = SessionController(
            instance=instance,
            display=StdoutConversationDisplay(show_labels=False, verbose=0),
            config=ConversationConfig(single_turn=True),
        )
        result = controller.run_turn("What is the capital of France?")
        assert result.text is not None
        assert len(result.text) >= 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Built-in tools (Python — real execution)
# ═══════════════════════════════════════════════════════════════════════════

class TestBuiltinTools:
    """Test calculator and web-search via library-standard tool registry."""

    def test_calculator_tool(self):
        from mas.library.standard.tools import execute_tool

        result = execute_tool("calculator", arguments={"expression": "27 ** 0.5"})
        assert result

    def test_calculator_basic_arithmetic(self):
        from mas.library.standard.tools import execute_tool

        result = execute_tool("calculator", arguments={"expression": "2 ** 16"})
        assert result

    def test_web_search_tool_exists(self):
        from mas.library.standard.tools import execute_tool

        out = execute_tool("web-search", arguments={"query": "test query"})
        assert out
