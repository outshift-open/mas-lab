#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine selection — explicit mock/live only; no silent SimulatedEngine fallback."""

from __future__ import annotations

import logging

import pytest

from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.session.engine_factory import (
    _resolve_model_option,
    _resolve_sampling_param,
    build_engine,
    resolve_model_name,
)
from mas.runtime.driver.mocks import AutoCtxAssembler


def test_build_engine_errors_without_infra_or_mock(monkeypatch, tmp_path):
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


def test_build_engine_resolves_infra_anchor_from_workspace_when_omitted(monkeypatch, tmp_path):
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    ws = WorkspaceConfig({}, tmp_path)
    monkeypatch.setattr(WorkspaceConfig, "load", lambda *a, **k: ws)
    monkeypatch.setattr(UserConfig, "load", lambda *a, **k: UserConfig({}))
    ctx = AutoCtxAssembler()
    manifest = {"spec": {"execution": {"mocking": {"enabled": True}}}}

    sel = build_engine(ctx, manifest, None, workspace=ws)
    assert sel.mode == "mock"


def test_build_engine_mock_mode_from_execution_flag(monkeypatch, tmp_path):
    from mas.ctl.infra.resolve import resolve_infra_refs
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    monkeypatch.setattr(WorkspaceConfig, "load", lambda *a, **k: WorkspaceConfig({}))
    monkeypatch.setattr(UserConfig, "load", lambda *a, **k: UserConfig({}))
    ctx = AutoCtxAssembler()
    manifest = {"spec": {"execution": {"mocking": {"enabled": True}}}}
    infra = resolve_infra_refs(["standard:mock-llm"], anchor=tmp_path)

    sel = build_engine(
        ctx,
        manifest,
        infra,
        anchor=tmp_path,
    )
    assert sel.mode == "mock"
    from mas.runtime.engine.leaf import leaf_engine
    from mas.runtime.engine.llm_live import LiveLlmEngine

    assert isinstance(leaf_engine(sel.engine), LiveLlmEngine)
    assert leaf_engine(sel.engine)._model_access is not None


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


def test_resolve_sampling_param_falls_back_to_deprecated_spec_llm(caplog):
    manifest = {"spec": {"llm": {"temperature": 0.2, "max_tokens": 4096}}}
    with caplog.at_level(logging.WARNING):
        assert _resolve_sampling_param(manifest, "temperature", 0.7) == 0.2
        assert _resolve_sampling_param(manifest, "max_tokens", 2000) == 4096
    assert "spec.llm is deprecated" in caplog.text


def test_resolve_model_option_from_spec_models():
    manifest = {"spec": {"models": [{"model": "gpt-4", "reasoning_effort": "low"}]}}
    assert _resolve_model_option(manifest, "reasoning_effort") == "low"
