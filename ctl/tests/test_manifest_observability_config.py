#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for observability format derivation from manifest plugins."""

from __future__ import annotations

from mas.ctl.session.manifest_config import derive_observability_format


def test_derive_format_native_only() -> None:
    assert derive_observability_format(["native"]) == "native"


def test_derive_format_otel_only() -> None:
    assert derive_observability_format(["otel"]) == "otel"


def test_derive_format_both_plugins() -> None:
    assert derive_observability_format(["native", "otel"]) == "both"


def test_derive_format_cli_override() -> None:
    assert derive_observability_format(["native"], cli_override="otel") == "otel"
