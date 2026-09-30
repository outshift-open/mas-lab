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
    refs = [t["ref"] for t in tools if isinstance(t, dict) and "ref" in t]
    system_tools = {t["name"] for t in tools if isinstance(t, dict) and t.get("kind") == "system"}
    assert "samples:tools/web-search.tool.yaml" in refs
    assert system_tools == {"request_human_input", "inform_user"}


def test_compile_cli_applies_override_after_file_overlay() -> None:
    runner = CliRunner()
    result = runner.invoke(
        compile_cmd,
        [
            str(TUTORIAL_1 / "agent.yaml"),
            "--override",
            'agent:spec.context.role="override role"',
            "--no-header",
        ],
    )

    assert result.exit_code == 0, result.output
    doc = yaml.safe_load(result.output)
    assert doc["spec"]["context"]["role"] == "override role"


def test_compile_cli_applies_mas_agent_selector_to_inlined_agent(tmp_path: Path) -> None:
    manifest = tmp_path / "mas.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "mas/v1",
                "kind": "MAS",
                "metadata": {"name": "selector-test"},
                "spec": {
                    "agency": {
                        "agents": [
                            {
                                "apiVersion": "mas/v1",
                                "kind": "Agent",
                                "id": "qa",
                                "metadata": {"name": "qa"},
                                "spec": {
                                    "description": "QA agent",
                                    "context": {"role": "base"},
                                },
                            }
                        ]
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        compile_cmd,
        [
            str(manifest),
            "--override",
            'mas:spec.agency.agents[id=qa].spec.context.role="selected"',
            "--layout",
            "bundle",
            "--no-defaults",
            "--no-header",
            "--no-validate",
        ],
    )

    assert result.exit_code == 0, result.output
    doc = yaml.safe_load(result.output)
    assert doc["spec"]["agency"]["agents"][0]["spec"]["context"]["role"] == "selected"


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
    assert agents[0]["metadata"]["name"] == "moderator"


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
