#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Smoke tests for ``mas-ctl validate``."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mas.ctl.cli.commands.validate import validate_cmd

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_MANIFEST = REPO_ROOT / "docs/tutorials/01-building-an-agent/agent.yaml"


def test_validate_agent_manifest_ok() -> None:
    runner = CliRunner()
    result = runner.invoke(validate_cmd, [str(AGENT_MANIFEST)])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_validate_missing_path_fails() -> None:
    runner = CliRunner()
    missing = REPO_ROOT / "does-not-exist-agent.yaml"
    result = runner.invoke(validate_cmd, [str(missing)])
    assert result.exit_code != 0


def test_validate_no_paths_usage_error() -> None:
    runner = CliRunner()
    result = runner.invoke(validate_cmd, [])
    assert result.exit_code == 1
    assert "usage" in result.output.lower()
