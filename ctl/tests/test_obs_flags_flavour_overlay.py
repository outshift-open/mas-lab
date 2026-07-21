#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for build_observability_flavour_overlay + its use in
resolve_observability_config (FT7 — docs/design/flavour-boundary.md).
"""

from __future__ import annotations

from mas.ctl.cli.obs_flags import build_observability_flavour_overlay, resolve_observability_config


class TestBuildObservabilityFlavourOverlay:
    def test_no_flags_returns_none(self) -> None:
        assert build_observability_flavour_overlay({"observability": ["native"]}, events=None, events_file=None) is None

    def test_events_false_patches_empty_plugin_list(self) -> None:
        overlay = build_observability_flavour_overlay({"observability": ["native"]}, events=False, events_file=None)
        assert overlay["spec"]["target"] == {"kind": "Flavour"}
        assert overlay["spec"]["patch"]["observability"] == []

    def test_events_true_defaults_to_native_when_flavour_silent(self) -> None:
        overlay = build_observability_flavour_overlay(None, events=True, events_file=None)
        assert overlay["spec"]["patch"]["observability"] == ["native"]

    def test_events_true_preserves_flavours_own_plugin_list(self) -> None:
        overlay = build_observability_flavour_overlay(
            {"observability": ["native", "otel"]}, events=True, events_file=None
        )
        assert overlay["spec"]["patch"]["observability"] == ["native", "otel"]

    def test_events_file_configures_native_path(self) -> None:
        overlay = build_observability_flavour_overlay(
            {"observability": ["native"]}, events=None, events_file="traces/custom.jsonl"
        )
        assert overlay["spec"]["patch"]["observability"] == [{"native": {"path": "traces/custom.jsonl"}}]

    def test_events_file_adds_native_when_not_already_selected(self) -> None:
        overlay = build_observability_flavour_overlay(
            {"observability": ["otel"]}, events=None, events_file="traces/custom.jsonl"
        )
        assert overlay["spec"]["patch"]["observability"] == ["otel", {"native": {"path": "traces/custom.jsonl"}}]

    def test_events_false_wins_over_events_file(self) -> None:
        overlay = build_observability_flavour_overlay(
            {"observability": ["native"]}, events=False, events_file="traces/custom.jsonl"
        )
        assert overlay["spec"]["patch"]["observability"] == []


class TestResolveObservabilityConfigMergesFlavourOverlay:
    def test_events_file_reflected_in_effective_flavour_and_config(self) -> None:
        cfg = resolve_observability_config(
            events=None,
            events_file="traces/custom.jsonl",
            events_stdout=False,
            events_format=None,
            manifest={"spec": {}},
            flavour_spec={"observability": ["native"]},
        )
        assert cfg.events_file == "traces/custom.jsonl"
        assert cfg.plugins == ["native"]

    def test_agent_declared_observability_is_not_overridden_by_flavour_overlay(self) -> None:
        # The agent manifest's own spec.observability still wins over the
        # (CLI-patched) flavour fallback — per-agent scoping is preserved.
        cfg = resolve_observability_config(
            events=None,
            events_file="traces/custom.jsonl",
            events_stdout=False,
            events_format=None,
            manifest={"spec": {"observability": ["otel"]}},
            flavour_spec={"observability": ["native"]},
        )
        assert cfg.plugins == ["otel"]
        # cli_events_file is still passed straight through to
        # observability_config_from_manifest (unconditional override, kept
        # for callers like mas.ctl.benchmark.runner.bench_obs_config).
        assert cfg.events_file == "traces/custom.jsonl"

    def test_no_cli_flags_leaves_flavour_untouched(self) -> None:
        cfg = resolve_observability_config(
            events=None,
            events_file=None,
            events_stdout=False,
            events_format=None,
            manifest={"spec": {}},
            flavour_spec={"observability": [{"native": {"path": "traces/from-flavour.jsonl"}}]},
        )
        assert cfg.events_file == "traces/from-flavour.jsonl"
