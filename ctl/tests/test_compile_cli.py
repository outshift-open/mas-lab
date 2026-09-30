#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Smoke tests for ``mas-ctl compile``."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner
from mas.ctl.cli.commands.compile import compile_cmd

REPO_ROOT = Path(__file__).resolve().parents[2]
TUTORIAL_1 = REPO_ROOT / "docs/tutorials/01-building-an-agent"
TUTORIAL_2 = REPO_ROOT / "docs/tutorials/02-creating-a-mas"


def test_compile_cli_stdout_tutorial_1() -> None:
    runner = CliRunner()
    result = runner.invoke(
        compile_cmd,
        [
            str(TUTORIAL_1 / "agent.yaml"),
            "-o",
            str(TUTORIAL_1 / "overlays/tools.yaml"),
            "--no-header",
        ],
    )
    assert result.exit_code == 0, result.output
    doc = yaml.safe_load(result.output)
    assert doc["kind"] == "Agent"
    tools = doc["spec"]["tools"]
    refs = [t["ref"] if isinstance(t, dict) else t for t in tools]
    assert "samples:tools/web-search.tool.yaml" in refs


def test_compile_cli_writes_agent_file(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "compiled.yaml"
    result = runner.invoke(
        compile_cmd,
        [
            str(TUTORIAL_1 / "agent.yaml"),
            "-o",
            str(TUTORIAL_1 / "overlays/skills.yaml"),
            "-O",
            str(out),
            "--no-header",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["spec"]["skills"] == ["answer-formatting"]


def test_compile_cli_mas_tree_and_bundle(tmp_path: Path) -> None:
    runner = CliRunner()
    tree_dir = tmp_path / "tree"
    result = runner.invoke(
        compile_cmd,
        [
            str(TUTORIAL_2 / "mas.yaml"),
            "-o",
            str(TUTORIAL_2 / "overlays/linear.yaml"),
            "-O",
            str(tree_dir),
            "--no-header",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tree_dir / "mas.yaml").is_file()
    assert (tree_dir / "agents/schedule-agent/agent.yaml").is_file()

    bundle = tmp_path / "team.yaml"
    result = runner.invoke(
        compile_cmd,
        [
            str(TUTORIAL_2 / "mas.yaml"),
            "-o",
            str(TUTORIAL_2 / "overlays/linear.yaml"),
            "--layout",
            "bundle",
            "-O",
            str(bundle),
            "--no-header",
        ],
    )
    assert result.exit_code == 0, result.output
    doc = yaml.safe_load(bundle.read_text(encoding="utf-8"))
    agents = doc["spec"]["agency"]["agents"]
    assert agents[0]["kind"] == "Agent"
    assert agents[0]["metadata"]["name"] == "schedule_agent"


def test_compile_cli_tree_to_yaml_file_fails() -> None:
    runner = CliRunner()
    result = runner.invoke(
        compile_cmd,
        [
            str(TUTORIAL_1 / "agent.yaml"),
            "--layout",
            "tree",
            "-O",
            "out.yaml",
        ],
    )
    assert result.exit_code == 1
    assert "directory" in result.output.lower()
