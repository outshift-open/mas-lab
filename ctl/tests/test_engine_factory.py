#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine selection — live or llm_cache replay; no silent SimulatedEngine fallback."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.session.engine_factory import (
    _cache_read_enabled,
    _resolve_model_option,
    _resolve_sampling_param,
    _stream_enabled,
    _strict_replay,
    build_engine,
    resolve_model_name,
)
from mas.runtime.driver.mocks import AutoCtxAssembler

_CI_REPLAY = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "llm-cache" / "ci-replay.yaml"


def test_build_engine_errors_without_infra(monkeypatch, tmp_path):
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    monkeypatch.setattr(WorkspaceConfig, "load", lambda *a, **k: WorkspaceConfig({}))
    monkeypatch.setattr(UserConfig, "load", lambda *a, **k: UserConfig({}))
    ctx = AutoCtxAssembler()
    manifest = {"spec": {"models": [{"model": "gpt-4o"}]}}

    with pytest.raises(RuntimeError, match="No LLM configured"):
        build_engine(
            ctx,
            manifest,
            ResolvedInfra(refs=[], llm_proxy={}),
            anchor=tmp_path,
        )


def test_build_engine_live_requires_api_key(monkeypatch, tmp_path):
    from mas.ctl.infra.resolve import resolve_infra_refs
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    monkeypatch.setattr(WorkspaceConfig, "load", lambda *a, **k: WorkspaceConfig({}))
    monkeypatch.setattr(UserConfig, "load", lambda *a, **k: UserConfig({}))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ctx = AutoCtxAssembler()
    infra = resolve_infra_refs(["standard:openai"], anchor=tmp_path)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is unset"):
        build_engine(ctx, {"spec": {}}, infra, anchor=tmp_path)


def test_parse_execution_rejects_removed_mocking_key():
    from mas.ctl.manifest.spec_bindings import SpecBindingError, parse_execution

    with pytest.raises(SpecBindingError, match="unknown field 'mocking'"):
        parse_execution({"mocking": {"enabled": True}})


def test_build_engine_replay_does_not_require_api_key(monkeypatch, tmp_path):
    from mas.ctl.infra.resolve import resolve_infra_refs
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    monkeypatch.setattr(WorkspaceConfig, "load", lambda *a, **k: WorkspaceConfig({}))
    monkeypatch.setattr(UserConfig, "load", lambda *a, **k: UserConfig({}))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ctx = AutoCtxAssembler()
    infra = resolve_infra_refs([str(_CI_REPLAY)], anchor=tmp_path)
    assert _strict_replay(infra.llm_proxy) is True

    sel = build_engine(ctx, {"spec": {}}, infra, anchor=tmp_path)
    assert sel.mode == "replay"


def test_resolve_sampling_param_prefers_spec_models():
    manifest = {
        "spec": {
            "models": [{"model": "gpt-4", "temperature": 0.1, "max_tokens": 8000}],
            "llm": {"temperature": 0.9, "max_tokens": 500},
        }
    }
    assert _resolve_sampling_param(manifest, "temperature", 0.7) == 0.1
    assert _resolve_sampling_param(manifest, "max_tokens", 2000) == 8000


def test_resolve_model_name_prefers_spec_models(monkeypatch):
    monkeypatch.delenv("MAS_CTL_MODEL", raising=False)
    monkeypatch.delenv("MAS_LLM_MODEL", raising=False)
    manifest = {
        "spec": {
            "models": [{"model": "vertex_ai/gemini-2.5-pro"}],
            "llm": {"model": "gpt-4o"},
        }
    }
    assert resolve_model_name(manifest, None) == "vertex_ai/gemini-2.5-pro"


def test_resolve_model_name_cli_override_beats_spec(monkeypatch):
    monkeypatch.delenv("MAS_CTL_MODEL", raising=False)
    monkeypatch.delenv("MAS_LLM_MODEL", raising=False)
    manifest = {"spec": {"models": [{"model": "gpt-4o"}]}}
    assert resolve_model_name(manifest, None, forced="gpt-4.1") == "gpt-4.1"


def test_resolve_sampling_param_falls_back_to_deprecated_spec_llm(caplog):
    manifest = {"spec": {"llm": {"temperature": 0.2, "max_tokens": 4096}}}
    with caplog.at_level(logging.WARNING):
        assert _resolve_sampling_param(manifest, "temperature", 0.7) == 0.2
        assert _resolve_sampling_param(manifest, "max_tokens", 2000) == 4096
    assert "spec.llm is deprecated" in caplog.text


def test_resolve_model_option_from_spec_models():
    manifest = {"spec": {"models": [{"model": "gpt-4", "reasoning_effort": "low"}]}}
    assert _resolve_model_option(manifest, "reasoning_effort") == "low"


def test_cache_and_stream_from_runtime_engine():
    rt = {"cache": {"read": False}, "stream": True}
    assert _cache_read_enabled(rt) is False
    assert _stream_enabled(rt) is True
