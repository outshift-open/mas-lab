#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mas-workspace env overrides."""

from mas.ctl.workspace.config import WorkspaceConfig, infra_refs_from_env


def test_infra_refs_from_env_empty(monkeypatch):
    monkeypatch.delenv("MAS_INFRA_REFS", raising=False)
    assert infra_refs_from_env() == []


def test_infra_refs_from_env_comma_and_space(monkeypatch):
    monkeypatch.setenv("MAS_INFRA_REFS", "standard:llm-proxy, standard:ollama")
    assert infra_refs_from_env() == ["standard:llm-proxy", "standard:ollama"]


def test_effective_infra_refs_env_overrides_workspace(monkeypatch):
    monkeypatch.setenv("MAS_INFRA_REFS", "standard:llm-proxy")
    ws = WorkspaceConfig({"infra_refs": ["standard:openai"]})
    assert ws.effective_infra_refs == ["standard:llm-proxy"]


def test_effective_infra_refs_falls_back_to_workspace(monkeypatch):
    monkeypatch.delenv("MAS_INFRA_REFS", raising=False)
    ws = WorkspaceConfig({"infra_refs": ["standard:openai"]})
    assert ws.effective_infra_refs == ["standard:openai"]
