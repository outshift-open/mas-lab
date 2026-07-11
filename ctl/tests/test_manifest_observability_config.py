#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for observability format derivation from manifest plugins."""

from __future__ import annotations

from mas.ctl.session.manifest_config import (
    derive_observability_format,
    observability_config_from_manifest,
)


def test_derive_format_native_only() -> None:
    assert derive_observability_format(["native"]) == "native"


def test_derive_format_otel_only() -> None:
    assert derive_observability_format(["otel"]) == "otel"


def test_derive_format_both_plugins() -> None:
    assert derive_observability_format(["native", "otel"]) == "both"


def test_derive_format_cli_override() -> None:
    assert derive_observability_format(["native"], cli_override="otel") == "otel"


class TestFlavourObservabilityFallback:
    """FT7 groundwork: flavour.spec.observability is the deployment-posture
    default when the agent/MAS manifest doesn't declare its own — see
    docs/design/flavour-boundary.md."""

    def test_flavour_supplies_plugins_when_manifest_silent(self) -> None:
        cfg = observability_config_from_manifest(
            {"spec": {}},
            flavour_spec={"observability": ["native"]},
        )
        assert cfg.plugins == ["native"]
        assert cfg.enabled is True

    def test_manifest_observability_wins_over_flavour(self) -> None:
        cfg = observability_config_from_manifest(
            {"spec": {"observability": ["otel"]}},
            flavour_spec={"observability": ["native"]},
        )
        assert cfg.plugins == ["otel"]

    def test_no_flavour_no_manifest_observability_disabled(self) -> None:
        cfg = observability_config_from_manifest({"spec": {}}, flavour_spec=None)
        assert cfg.plugins == []
        assert cfg.enabled is False

    def test_cli_events_file_overrides_flavour_native_path(self) -> None:
        cfg = observability_config_from_manifest(
            {"spec": {}},
            flavour_spec={"observability": [{"native": {"path": "traces/from-flavour.jsonl"}}]},
            cli_events_file="traces/from-cli.jsonl",
        )
        assert cfg.events_file == "traces/from-cli.jsonl"
