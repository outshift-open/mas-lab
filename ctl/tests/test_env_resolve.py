#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""infra/env_resolve.py — env: indirection resolution and its log levels."""

from __future__ import annotations

import logging

from mas.ctl.infra.env_resolve import resolve_env_string


def test_resolves_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MAS_TEST_ENV_RESOLVE_VAR", "resolved-value")
    assert resolve_env_string("env:MAS_TEST_ENV_RESOLVE_VAR") == "resolved-value"


def test_non_env_prefixed_value_passes_through_unchanged() -> None:
    assert resolve_env_string("https://example.com") == "https://example.com"


def test_unset_var_with_default_uses_default_and_logs_debug(monkeypatch, caplog) -> None:
    monkeypatch.delenv("MAS_TEST_ENV_RESOLVE_UNSET", raising=False)
    with caplog.at_level(logging.DEBUG, logger="mas.ctl.infra.env_resolve"):
        value = resolve_env_string("env:MAS_TEST_ENV_RESOLVE_UNSET|fallback-value")
    assert value == "fallback-value"
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)
    assert any("using default value" in r.message for r in caplog.records)


def test_unset_var_with_no_default_returns_empty_and_logs_warning(monkeypatch, caplog) -> None:
    monkeypatch.delenv("MAS_TEST_ENV_RESOLVE_UNSET_NO_DEFAULT", raising=False)
    with caplog.at_level(logging.DEBUG, logger="mas.ctl.infra.env_resolve"):
        value = resolve_env_string("env:MAS_TEST_ENV_RESOLVE_UNSET_NO_DEFAULT")
    assert value == ""
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_env_prefix_with_no_var_name_returns_empty() -> None:
    assert resolve_env_string("env:") == ""
