#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine selection — explicit mock/live only; no silent SimulatedEngine fallback."""

from __future__ import annotations

import pytest

from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.session.engine_factory import build_engine
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
