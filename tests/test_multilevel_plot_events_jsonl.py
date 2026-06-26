#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Multilevel trajectory plot from native events.jsonl (OSS path)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EVENTS_FIXTURE = (
    REPO_ROOT / "docs/tutorials/03-experiments-and-analysis/fixtures/events.jsonl"
)


@pytest.mark.parametrize("fmt", ["html", "svg"])
def test_multilevel_plot_renders_from_events_jsonl(fmt: str, tmp_path: Path) -> None:
    pytest.importorskip("mas.lab.plots.multilevel_trajectory")
    from mas.lab.plots.multilevel_trajectory import plot_multilevel_trajectory
    from mas.lab.plots.trajectory import load_trace

    assert EVENTS_FIXTURE.is_file(), f"missing fixture: {EVENTS_FIXTURE}"
    events = load_trace(EVENTS_FIXTURE)
    assert events, "fixture events.jsonl should not be empty"

    rendered = plot_multilevel_trajectory(events, fmt=fmt, title="Tutorial 03 fixture")
    assert len(rendered) > 200
    if fmt == "html":
        assert "<" in rendered
    else:
        assert "<svg" in rendered

    out = tmp_path / f"multilevel.{fmt if fmt != 'html' else 'html'}"
    out.write_text(rendered, encoding="utf-8")
    assert out.stat().st_size > 200


def test_multilevel_cli_from_events_jsonl(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from mas.lab.cli import app as cli

    runner = CliRunner()
    out = tmp_path / "swimlane.html"
    result = runner.invoke(
        cli,
        [
            "plot",
            "multilevel-trajectory",
            str(EVENTS_FIXTURE),
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert out.stat().st_size > 200
