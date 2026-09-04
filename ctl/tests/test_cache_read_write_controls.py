#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""_cache_read_enabled/_cache_write_enabled: precedence is CLI override ->
spec.execution.cache.enabled (hard kill-switch) -> spec.execution.cache.
read/write -> MAS_LLM_CACHE_READ/MAS_LLM_CACHE_WRITE env var -> default true."""

from __future__ import annotations

from mas.ctl.manifest.spec_bindings import parse_execution
from mas.ctl.session.engine_factory import _cache_read_enabled, _cache_write_enabled


def _manifest(cache: dict) -> dict:
    return {"spec": {"execution": {"cache": cache}}}


def test_defaults_to_true_with_no_manifest_or_env():
    assert _cache_read_enabled(None) is True
    assert _cache_write_enabled(None) is True


def test_manifest_read_write_fields_are_independent():
    manifest = _manifest({"read": False, "write": True})
    assert _cache_read_enabled(manifest) is False
    assert _cache_write_enabled(manifest) is True


def test_enabled_false_is_a_hard_kill_switch_for_both():
    manifest = _manifest({"enabled": False, "read": True, "write": True})
    assert _cache_read_enabled(manifest) is False
    assert _cache_write_enabled(manifest) is False


def test_env_var_used_when_manifest_silent(monkeypatch):
    monkeypatch.setenv("MAS_LLM_CACHE_READ", "false")
    monkeypatch.setenv("MAS_LLM_CACHE_WRITE", "true")
    assert _cache_read_enabled(None) is False
    assert _cache_write_enabled(None) is True


def test_manifest_field_wins_over_env_var(monkeypatch):
    monkeypatch.setenv("MAS_LLM_CACHE_READ", "false")
    manifest = _manifest({"read": True})
    assert _cache_read_enabled(manifest) is True


def test_cli_override_wins_over_everything(monkeypatch):
    monkeypatch.setenv("MAS_LLM_CACHE_READ", "true")
    manifest = _manifest({"enabled": False, "read": True})
    assert _cache_read_enabled(manifest, override=False) is False
    assert _cache_write_enabled(manifest, override=True) is True


def test_manifest_read_write_fields_pass_schema_validation():
    """spec.execution.cache.read/write must actually validate -- a manifest
    declaring them, not just an env var or CLI flag, is one of the three
    documented ways to set this."""
    parse_execution({"cache": {"enabled": True, "read": False, "write": True}})
