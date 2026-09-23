#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Human-default --trace (summary + timestamps) vs --trace full."""

from __future__ import annotations

import click
from click.testing import CliRunner
from mas.ctl.cli.trace_flags import mas_ctl_from_configs, resolve_trace_settings, trace_options


def test_trace_defaults_to_summary_with_timestamps_no_color():
    s = resolve_trace_settings(trace_mode="summary")
    assert s.enabled is True
    assert s.summary is True
    assert s.timestamps is True
    assert s.color is False
    assert s.engine is False


def test_trace_full_is_verbose_dump_with_timestamps():
    s = resolve_trace_settings(trace_mode="full")
    assert s.enabled is True
    assert s.summary is False
    assert s.timestamps is True
    assert s.color is False


def test_no_trace_wins_over_config():
    s = resolve_trace_settings(no_trace=True, mas_ctl={"trace": "summary"})
    assert s.enabled is False
    assert s.summary is False
    assert s.timestamps is False


def test_config_yaml_enables_summary_without_flags():
    s = resolve_trace_settings(mas_ctl={"trace": "summary"})
    assert s.enabled is True
    assert s.summary is True
    assert s.timestamps is True
    assert s.color is False


def test_config_true_means_summary():
    s = resolve_trace_settings(mas_ctl={"trace": True})
    assert s.enabled is True
    assert s.summary is True


def test_workspace_mas_ctl_wins_over_user():
    merged = mas_ctl_from_configs({"trace": "full", "trace_color": True}, {"trace": "summary"})
    assert merged["trace"] == "summary"
    assert merged["trace_color"] is True
    s = resolve_trace_settings(mas_ctl=merged)
    assert s.summary is True
    assert s.color is True


def test_cli_full_overrides_config_summary():
    s = resolve_trace_settings(trace_mode="full", mas_ctl={"trace": "summary"})
    assert s.summary is False
    assert s.enabled is True


def test_config_color_opt_in():
    s = resolve_trace_settings(mas_ctl={"trace": "summary", "trace_color": True})
    assert s.color is True


def test_cli_no_color_overrides_config():
    s = resolve_trace_settings(
        trace_mode="summary",
        trace_color=False,
        mas_ctl={"trace_color": True},
    )
    assert s.color is False


def test_no_trace_timestamps():
    s = resolve_trace_settings(trace_mode="summary", trace_timestamps=False)
    assert s.timestamps is False


def test_trace_summary_alias_enables_summary():
    s = resolve_trace_settings(trace_summary=True)
    assert s.enabled is True
    assert s.summary is True
    assert s.timestamps is True


def test_trace_full_alias_enables_dump():
    s = resolve_trace_settings(trace_full=True)
    assert s.enabled is True
    assert s.summary is False


def test_off_by_default():
    s = resolve_trace_settings()
    assert s.enabled is False
    assert s.as_session_kwargs()["trace"] is False


@click.command()
@trace_options
def _probe(trace_mode, no_trace, trace_timestamps, trace_engine, trace_summary, trace_full, trace_color):
    s = resolve_trace_settings(
        trace_mode=trace_mode,
        no_trace=no_trace,
        trace_summary=trace_summary,
        trace_full=trace_full,
        trace_timestamps=trace_timestamps,
        trace_engine=trace_engine,
        trace_color=trace_color,
    )
    click.echo(f"{s.enabled}:{s.summary}:{s.timestamps}:{s.color}:{s.engine}")


def test_click_bare_trace_is_summary():
    result = CliRunner().invoke(_probe, ["--trace"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "True:True:True:False:False"


def test_click_trace_full_optional_value():
    result = CliRunner().invoke(_probe, ["--trace", "full"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "True:False:True:False:False"


def test_click_trace_leaves_following_path_alone():
    result = CliRunner().invoke(_probe, ["--trace", "--trace-color"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "True:True:True:True:False"


def test_click_no_trace_timestamps():
    result = CliRunner().invoke(_probe, ["--trace", "--no-trace-timestamps"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "True:True:False:False:False"
