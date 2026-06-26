#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for MASExperimentConfig.from_yaml — dataset parsing and lab smoke checks.

Covers:
  - dataset: path: <file>        (classic form, must keep working)
  - dataset: name: <name>        (shorthand, was broken — KeyError: 'path')
  - dataset: name: + mode:       (extensions.lab dataset shorthand)
  - dataset: absent              (optional dataset, valid)
  - Smoke-parse of every real experiment.yaml in labs/
  - Dry-run of every reproduce command (validates config + pipeline end-to-end)
"""
import subprocess
import textwrap
import warnings
from pathlib import Path

import pytest
import yaml

from mas.lab.lab.config import MASExperimentConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LABS_DIR = Path(__file__).parents[3] / "labs"
"""Root of the labs/ tree, relative to the repo root."""


def _write_experiment(tmp_path: Path, dataset_block: str, extra: str = "") -> Path:
    """Write a minimal well-formed experiment.yaml with the given dataset block."""
    # Create a placeholder mas.yaml so path resolution does not raise
    mas_yaml = tmp_path / "mas.yaml"
    mas_yaml.write_text("apiVersion: mas/v1\nkind: MAS\nmetadata:\n  name: test-mas\n")

    # Build dataset section — indent every line by 2 spaces to nest under experiment:
    dataset_indented = "\n".join("  " + line for line in dataset_block.splitlines())
    extra_section = ("\n" + "\n".join("  " + line for line in extra.splitlines())) if extra else ""

    exp = (
        "experiment:\n"
        "  name: test-experiment\n"
        '  description: "Unit test"\n'
        "\n"
        "  applications:\n"
        "    - manifest: ./mas.yaml\n"
        "      configs_dir: ./overlays\n"
        "\n"
        f"{dataset_indented}\n"
        f"{extra_section}\n"
    )
    exp_yaml = tmp_path / "experiment.yaml"
    exp_yaml.write_text(exp)
    return exp_yaml


def _make_dataset_file(base: Path, filename: str) -> None:
    """Create a minimal dataset YAML at base/datasets/<filename>."""
    datasets_dir = base / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "apiVersion": "lab/v1",
        "kind": "Dataset",
        "metadata": {"name": Path(filename).stem, "version": "1.0"},
        "spec": {"items": [{"id": "q1", "prompt": "Test query"}]},
    }
    (datasets_dir / filename).write_text(
        yaml.dump(manifest, allow_unicode=True, sort_keys=False)
    )


# ---------------------------------------------------------------------------
# dataset: path: (classic form — must keep working)
# ---------------------------------------------------------------------------

def test_dataset_path_form(tmp_path):
    """dataset: path: <relative> resolves correctly."""
    _make_dataset_file(tmp_path, "my-queries.yaml")
    exp_yaml = _write_experiment(
        tmp_path,
        "dataset:\n  path: ./datasets/my-queries.yaml",
    )
    cfg = MASExperimentConfig.from_yaml(exp_yaml)
    assert cfg.dataset == (tmp_path / "datasets" / "my-queries.yaml").resolve()


# ---------------------------------------------------------------------------
# dataset: name: (shorthand — was the bug)
# ---------------------------------------------------------------------------

def test_dataset_name_only_resolves_to_datasets_folder(tmp_path):
    """dataset: name: <foo> → ./datasets/foo.yaml relative to experiment dir."""
    _make_dataset_file(tmp_path, "extensions-queries.yaml")
    exp_yaml = _write_experiment(
        tmp_path,
        "dataset:\n  name: extensions-queries",
    )
    cfg = MASExperimentConfig.from_yaml(exp_yaml)
    assert cfg.dataset == (tmp_path / "datasets" / "extensions-queries.yaml").resolve()


def test_dataset_name_with_extra_fields(tmp_path):
    """dataset: name: + mode: (real extensions.lab shape) no longer raises KeyError."""
    _make_dataset_file(tmp_path, "extensions-queries.yaml")
    exp_yaml = _write_experiment(
        tmp_path,
        "dataset:\n  name: extensions-queries\n  mode: sequential",
    )
    # This was crashing with KeyError: 'path' before the fix
    cfg = MASExperimentConfig.from_yaml(exp_yaml)
    assert cfg.dataset is not None
    assert cfg.dataset.name == "extensions-queries.yaml"


def test_dataset_name_with_limit(tmp_path):
    """dataset: name: + limit: are both parsed without error."""
    _make_dataset_file(tmp_path, "queries.yaml")
    exp_yaml = _write_experiment(
        tmp_path,
        "dataset:\n  name: queries\n  limit: 5",
    )
    cfg = MASExperimentConfig.from_yaml(exp_yaml)
    assert cfg.dataset_limit == 5


def test_dataset_name_with_group_filter(tmp_path):
    """dataset: name: + group: shorthand populates dataset_filter correctly."""
    _make_dataset_file(tmp_path, "queries.yaml")
    exp_yaml = _write_experiment(
        tmp_path,
        "dataset:\n  name: queries\n  group: single_agent",
    )
    cfg = MASExperimentConfig.from_yaml(exp_yaml)
    assert cfg.dataset_filter == {"group": "single_agent"}


def test_plots_key_rejected(tmp_path):
    """Top-level plots: is deprecated — use pipeline post steps instead."""
    exp_yaml = _write_experiment(
        tmp_path,
        "",
        extra="plots:\n  latency:\n    type: latency_by_scenario",
    )
    with pytest.raises(ValueError, match="plots"):
        MASExperimentConfig.from_yaml(exp_yaml)


# ---------------------------------------------------------------------------
# No dataset (optional)
# ---------------------------------------------------------------------------

def test_no_dataset_is_valid(tmp_path):
    """Omitting dataset entirely is a valid experiment (scenarios-driven)."""
    mas_yaml = tmp_path / "mas.yaml"
    mas_yaml.write_text("apiVersion: mas/v1\nkind: MAS\nmetadata:\n  name: test\n")
    exp_yaml = tmp_path / "experiment.yaml"
    exp_yaml.write_text(textwrap.dedent("""\
        experiment:
          name: no-dataset
          description: "No dataset — scenarios only"
          applications:
            - manifest: ./mas.yaml
              configs_dir: ./overlays
    """))
    cfg = MASExperimentConfig.from_yaml(exp_yaml)
    assert cfg.dataset is None


# ---------------------------------------------------------------------------
# Smoke-parse: every real experiment.yaml in labs/
# ---------------------------------------------------------------------------

def _collect_lab_experiments() -> list[tuple[str, Path]]:
    """Return (label, path) pairs for all experiment.yaml files under labs/."""
    if not _LABS_DIR.exists():
        return []
    return [
        (str(p.relative_to(_LABS_DIR)), p)
        for p in sorted(_LABS_DIR.rglob("experiment.yaml"))
    ]


@pytest.mark.parametrize("label,exp_yaml", _collect_lab_experiments(), ids=[p[0] for p in _collect_lab_experiments()])
def test_lab_experiment_yaml_parses(label, exp_yaml):
    """Every experiment.yaml in labs/ must parse without errors.

    This catches schema regressions (missing fields, unexpected keys,
    KeyErrors like the 'path' bug) before contributors discover them at
    run time.  The test does NOT execute the experiment — it only validates
    that MASExperimentConfig.from_yaml() succeeds.

    Warnings (e.g. deprecated output_dir) are allowed; errors are not.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        cfg = MASExperimentConfig.from_yaml(exp_yaml)

    assert cfg.name, f"{label}: experiment name must be non-empty"
    # If a dataset block is present the path must have been resolved
    if cfg.dataset is not None:
        assert isinstance(cfg.dataset, Path), f"{label}: dataset must resolve to a Path"


# ---------------------------------------------------------------------------
# Dry-run: every reproduce command must pass `mas-lab benchmark run --dry-run`
#
# This is the strongest validation short of actually running the experiments:
# it exercises the full config-loading, scenario discovery, dataset resolution,
# and pipeline planning code path.  Safe to run without any API keys.
# ---------------------------------------------------------------------------

#: Experiments listed in `task reproduce` — the exact commands an experimenter runs.
_REPRODUCE_EXPERIMENTS = [
    "labs/design-space.lab/01-design-patterns/experiment.yaml",
    "labs/design-space.lab/02-topologies/experiment.yaml",
    "labs/lifecycle-control.lab/experiment.yaml",
    "labs/extensions.lab/experiment.yaml",
]

_REPO_ROOT = Path(__file__).parents[3]
"""Absolute path to the repository root (outshift-open/mas-lab)."""


@pytest.mark.parametrize("rel_path", _REPRODUCE_EXPERIMENTS)
def test_reproduce_command_dry_run(rel_path: str):
    """``mas-lab benchmark run <experiment> --dry-run`` must exit 0 and report valid config.

    Runs the actual CLI in a subprocess so the test exercises the same code
    path as an experimenter, including config loading, path resolution,
    dataset discovery, and pipeline planning.  No LLM calls are made.
    """
    exp_yaml = _REPO_ROOT / rel_path
    assert exp_yaml.exists(), f"Experiment YAML not found: {exp_yaml}"

    result = subprocess.run(
        ["mas-lab", "benchmark", "run", str(exp_yaml), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"`mas-lab benchmark run {rel_path} --dry-run` exited with code "
        f"{result.returncode}.\n\nOutput:\n{output}"
    )
    assert "Configuration valid" in output, (
        f"`--dry-run` did not print 'Configuration valid' for {rel_path}.\n\nOutput:\n{output}"
    )
