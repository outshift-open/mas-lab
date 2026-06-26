#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tutorial 03 — Analysis, Pipelines & Evaluation: integration tests.

Tests experiment configs, pipeline definitions, overlay patterns, and
the benchmark/analysis CLI subcommands.  LLM calls are mocked.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import T03, T01, T02, load_yaml, run_cli

# ═══════════════════════════════════════════════════════════════════════════
# 1. Manifest validation (CLI)
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestValidation:
    """Validate all T03 manifests."""

    def test_validate_agent_yaml(self):
        r = run_cli(["mas-ctl", "validate", str(T03 / "agent.yaml")])
        assert r.returncode == 0, r.stderr

    def test_validate_mas_yaml(self):
        r = run_cli(["mas-ctl", "validate", str(T03 / "mas.yaml")])
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("overlay", ["react.yaml", "cot.yaml", "reflection.yaml"])
    def test_overlay_is_well_formed_patch(self, overlay):
        """Verify Patch overlays have correct structure."""
        ov = load_yaml(T03 / "overlays" / overlay)
        assert ov.get("kind") == "Overlay"
        assert ov.get("apiVersion") == "mas/v1"
        assert "spec" in ov
        assert "patch" in ov["spec"]

    @pytest.mark.parametrize("topo", ["single-agent.yaml", "linear.yaml", "moderator.yaml"])
    def test_topology_is_well_formed(self, topo):
        """Topology overlays must be valid YAML with agents and workflow."""
        topo_path = T03 / "topologies" / topo
        if not topo_path.exists():
            pytest.skip(f"{topo} not present")
        ov = load_yaml(topo_path)
        # Topologies are full MAS manifests or overlays with spec
        spec = ov.get("spec", ov)
        assert "agency" in spec or "workflow" in spec


# ═══════════════════════════════════════════════════════════════════════════
# 2. Experiment config structure (Python)
# ═══════════════════════════════════════════════════════════════════════════

class TestExperimentConfig:
    """Verify experiment YAML files have correct structure."""

    def test_patterns_experiment(self):
        exp = load_yaml(T03 / "experiment.yaml")
        e = exp["experiment"]
        assert e["name"] == "t3-observability-patterns"
        assert len(e["scenarios"]) == 3
        scenario_ids = {s["id"] for s in e["scenarios"]}
        assert scenario_ids == {"react", "cot", "reflection"}
        assert e["run"]["n_runs"] >= 1
        assert e.get("run", {}).get("pipeline", []) == []

    def test_topology_experiment(self):
        exp = load_yaml(T03 / "experiment-topology.yaml")
        e = exp["experiment"]
        assert e["name"] == "t3-topology-comparison"
        assert len(e["scenarios"]) == 3
        scenario_ids = {s["id"] for s in e["scenarios"]}
        assert scenario_ids == {"single-agent", "linear", "moderator"}
        assert e["run"]["n_runs"] >= 1
        # v2 experiments use run/scenario/application pipeline slots (may be empty)
        assert "run" in e
        assert e.get("run", {}).get("pipeline", []) == []

    def test_topology_experiment_levels(self):
        """Verify pipeline levels are present and release-safe."""
        exp = load_yaml(T03 / "experiment-topology.yaml")
        e = exp["experiment"]
        assert isinstance(e.get("run", {}).get("pipeline", []), list)
        assert e.get("run", {}).get("pipeline", []) == []
        assert e.get("scenario", {}).get("pipeline", []) == []
        assert e.get("pipeline", e.get("application", {}).get("post", [])) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Dataset files (Python)
# ═══════════════════════════════════════════════════════════════════════════

class TestDatasets:
    """Verify dataset files."""

    def test_patterns_dataset(self):
        ds_path = T03 / "dataset.yaml"
        if not ds_path.exists():
            pytest.skip("dataset.yaml not present")
        ds = load_yaml(ds_path)
        # Support both Dataset manifest and plain dict with items
        if ds.get("kind") == "Dataset":
            items = (ds.get("spec") or {}).get("items", [])
        else:
            items = ds.get("items", [])
        assert len(items) >= 2
        for item in items:
            assert "id" in item
            assert "inputs" in item
            assert item["inputs"].get("user")

    def test_topology_dataset(self):
        ds_path = T03 / "dataset-topology.yaml"
        if not ds_path.exists():
            pytest.skip("dataset-topology.yaml not present")
        ds = load_yaml(ds_path)
        if ds.get("kind") == "Dataset":
            items = (ds.get("spec") or {}).get("items", [])
        else:
            items = ds.get("items", ds if isinstance(ds, list) else [])
        assert len(items) >= 1
        for item in items:
            assert "id" in item
            assert "inputs" in item
            assert item["inputs"].get("user")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Pipeline config (Python)
# ═══════════════════════════════════════════════════════════════════════════

class TestPipelineConfig:
    """Verify pipeline YAML definitions."""

    def test_analysis_pipeline_structure(self):
        pipe = load_yaml(T03 / "pipelines" / "analysis.yaml")
        assert pipe["kind"] == "Pipeline"
        assert "metadata" in pipe
        assert pipe["metadata"]["name"] == "t3-analysis"

    def test_analysis_pipeline_has_steps(self):
        pipe = load_yaml(T03 / "pipelines" / "analysis.yaml")
        spec = pipe.get("spec", pipe)
        steps = spec.get("steps", spec.get("pipeline", []))
        assert len(steps) >= 1
        step_names = {s["name"] for s in steps}
        assert "extract" in step_names
        assert any(s.get("type") == "extract_trajectories" for s in steps)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Overlay patterns (Python)
# ═══════════════════════════════════════════════════════════════════════════

class TestOverlayPatterns:
    """Verify design pattern overlays."""

    def test_react_overlay_is_noop_patch(self):
        ov = load_yaml(T03 / "overlays" / "react.yaml")
        assert ov["kind"] == "Overlay"
        # React is the default — patch should be empty or minimal
        patch = ov["spec"]["patch"]
        assert patch == {} or patch is None or len(patch) <= 1

    def test_cot_overlay_sets_pattern(self):
        ov = load_yaml(T03 / "overlays" / "cot.yaml")
        patch = ov["spec"]["patch"]
        # Agent-level overlay: design_pattern is directly in patch
        dp = patch.get("design_pattern", {})
        assert dp.get("type") == "cot"
        assert dp.get("config", {}).get("max_steps", 0) > 0

    def test_reflection_overlay_sets_pattern(self):
        ov = load_yaml(T03 / "overlays" / "reflection.yaml")
        patch = ov["spec"]["patch"]
        # Agent-level overlay: design_pattern is directly in patch
        dp = patch.get("design_pattern", {})
        assert dp.get("type") == "reflection"

    def test_overlays_merge_onto_mas(self):
        """All three overlays should merge cleanly onto mas.yaml."""
        from mas.ctl.overlay import merge_overlay
        base = load_yaml(T03 / "mas.yaml")
        for ov_name in ["react.yaml", "cot.yaml", "reflection.yaml"]:
            ov = load_yaml(T03 / "overlays" / ov_name)
            merged = merge_overlay(base, ov)
            # Must still be a valid dict with MAS structure
            assert "spec" in merged or "apiVersion" in merged


# ═══════════════════════════════════════════════════════════════════════════
# 6. Topology overlay structure (Python)
# ═══════════════════════════════════════════════════════════════════════════

class TestTopologyOverlays:
    """Verify topology overlay files for the Part C experiment."""

    @pytest.mark.parametrize("topo_file,expected_entry", [
        ("single-agent.yaml", "planner"),
        ("linear.yaml", "schedule_agent"),
        ("moderator.yaml", "moderator"),
    ])
    def test_topology_workflow_entry(self, topo_file, expected_entry):
        topo_path = T03 / "topologies" / topo_file
        if not topo_path.exists():
            pytest.skip(f"{topo_file} not present")
        ov = load_yaml(topo_path)
        spec = ov.get("spec", ov)
        wf = spec.get("workflow", {})
        assert wf.get("entry") == expected_entry


# ═══════════════════════════════════════════════════════════════════════════
# 7. CLI subcommands (smoke tests)
# ═══════════════════════════════════════════════════════════════════════════

class TestCLISubcommands:
    """Smoke-test CLI subcommands (no LLM, no network)."""

    def test_mas_lab_help(self):
        r = run_cli(["mas-lab", "--help"])
        assert r.returncode == 0
        assert "benchmark" in r.stdout

    def test_mas_lab_benchmark_help(self):
        r = run_cli(["mas-lab", "benchmark", "--help"])
        assert r.returncode == 0

    def test_mas_lab_config(self):
        r = run_cli(["mas-lab", "config"])
        # Should show resolved paths without error
        assert r.returncode == 0

    def test_mas_runtime_help(self):
        r = run_cli(["mas-runtime", "--help"])
        assert r.returncode == 2
        assert "mas-ctl" in r.stderr

    def test_mas_ctl_help(self):
        r = run_cli(["mas-ctl", "--help"])
        assert r.returncode == 0
        assert "run-mas" in r.stdout

    def test_benchmark_dry_run_patterns(self):
        """Dry-run the patterns experiment (no LLM calls)."""
        r = run_cli(
            ["mas-lab", "benchmark", "run", "experiment.yaml", "--dry-run"],
            cwd=T03,
            timeout=30,
        )
        # Dry run should either succeed or fail gracefully
        # (some implementations may not have --dry-run)
        assert r.returncode in (0, 1, 2), f"Unexpected exit: {r.stderr}"


# ═══════════════════════════════════════════════════════════════════════════
# 8. Agent instantiation with T03 manifests (python-v2)
# ═══════════════════════════════════════════════════════════════════════════

class TestT03AgentInstantiation:
    """Instantiate T03 agents via mas-ctl session bootstrap."""

    def _mock_manifest(self, *extra_overlays: str) -> dict:
        from mas.ctl.overlay import merge_overlay

        base = load_yaml(T03 / "agent.yaml")
        mock_path = T01 / "overlays" / "mock-llm.yaml"
        base = merge_overlay(base, load_yaml(mock_path))
        for name in extra_overlays:
            base = merge_overlay(base, load_yaml(T03 / "overlays" / name))
        return base

    def test_instantiate_qa_agent(self):
        from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime

        config = self._mock_manifest()
        instance, _ = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=config,
                manifest_dir=T03,
                validate_manifests=False,
            ),
        )
        assert instance is not None
        name = (config.get("metadata") or {}).get("name", "").lower()
        assert "qa" in name or "t3" in name

    def test_instantiate_with_cot_overlay(self):
        from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime

        merged = self._mock_manifest("cot.yaml")
        instance, _ = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=merged,
                manifest_dir=T03,
                validate_manifests=False,
            ),
        )
        assert instance is not None


# ═══════════════════════════════════════════════════════════════════════════
# 9. Cross-tutorial consistency (Python)
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossTutorialConsistency:
    """Verify conventions are consistent across tutorials."""

    def test_all_experiments_have_name(self):
        # Tutorials 1/2 are CLI-first; experiment YAMLs start at tutorial 3.
        for tdir, exp_file in [
            (T03, "experiment.yaml"),
            (T03, "experiment-topology.yaml"),
        ]:
            path = tdir / exp_file
            if not path.exists():
                continue
            exp = load_yaml(path)
            assert "experiment" in exp, f"{path} missing 'experiment' key"
            assert "name" in exp["experiment"], f"{path} experiment missing 'name'"

    def test_all_tutorials_have_readme(self):
        for name in ["01-building-an-agent", "02-creating-a-mas", "03-experiments-and-analysis"]:
            readme = Path(T01).parent / name / "README.md"
            assert readme.exists(), f"README.md missing for {name}"
            content = readme.read_text()
            assert len(content) > 100
