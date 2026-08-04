#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mas.lab.cli import app


def test_init_yes_creates_config_and_default_infra(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code == 0, result.output
    cfg = tmp_path / "mas" / "config.yaml"
    infra = tmp_path / "mas" / "infra" / "llmprovider.yaml"

    assert cfg.exists()
    assert infra.exists()
    assert "infra_refs" in cfg.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in infra.read_text(encoding="utf-8")
    assert "How to proceed:" in result.output


def test_init_interactive_skip_infra(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(app, ["init"], input="n\n")

    assert result.exit_code == 0, result.output
    cfg = tmp_path / "mas" / "config.yaml"
    infra_dir = tmp_path / "mas" / "infra"

    assert cfg.exists()
    assert "infra_refs" not in cfg.read_text(encoding="utf-8")
    assert not infra_dir.exists()
    assert "infra : skipped" in result.output


def test_init_interactive_custom_provider(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["init"],
        input="y\nmyprovider\nhttps://example.llm/v1\nMY_API_KEY\ntrip-model\nopenai/gpt-4o-mini\n",
    )

    assert result.exit_code == 0, result.output
    cfg = tmp_path / "mas" / "config.yaml"
    infra = tmp_path / "mas" / "infra" / "myprovider.yaml"

    assert cfg.exists()
    assert infra.exists()
    cfg_text = cfg.read_text(encoding="utf-8")
    infra_text = infra.read_text(encoding="utf-8")
    assert "myprovider" in cfg_text
    assert "https://example.llm/v1" in infra_text
    assert "MY_API_KEY" in infra_text
    assert "trip-model: openai/gpt-4o-mini" in infra_text
    assert "mas-ctl run-mas library-samples/apps/trip-planner/mas.yaml" in result.output
    assert "Default trace file for this manifest" in result.output
    assert "--events-file traces/trip-planner-default.events.jsonl" in result.output
    assert "--trace --trace-summary --trace-color" in result.output
    assert "mas-lab telemetry show library-samples/apps/trip-planner/traces/events.jsonl" in result.output
    assert "mas-lab plot trajectory library-samples/apps/trip-planner/traces/events.jsonl" in result.output


def test_init_refuses_overwrite_with_yes(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()

    cfg = tmp_path / "mas" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("mas_lab:\n  flavour: old\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert "rerun without --yes" in result.output


def test_init_interactive_decline_overwrite_keeps_existing(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    runner = CliRunner()

    cfg = tmp_path / "mas" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    original = "mas_lab:\n  flavour: old\n"
    cfg.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init"], input="n\nn\n")

    assert result.exit_code == 0, result.output
    assert cfg.read_text(encoding="utf-8") == original
