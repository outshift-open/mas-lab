#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""instantiate_runtime() wires spec.working_memory.compaction into context_manager."""

from pathlib import Path

from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime


def _instantiate(manifest: dict, tmp_path: Path, monkeypatch):
    from mas.ctl.infra.resolve import resolve_infra_refs
    from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

    monkeypatch.setattr(WorkspaceConfig, "load", lambda *a, **k: WorkspaceConfig({}))
    monkeypatch.setattr(UserConfig, "load", lambda *a, **k: UserConfig({}))
    infra = resolve_infra_refs(["standard:mock-llm"], anchor=tmp_path)
    return instantiate_runtime(
        InstantiationOptions(
            agent_manifest=manifest,
            manifest_dir=tmp_path,
            resolved_infra=infra,
            enable_observability=False,
            enable_governance=False,
        )
    )


def test_keep_recent_compaction_is_wired_into_the_manifests_context_manager(tmp_path: Path, monkeypatch):
    manifest = {
        "metadata": {"name": "agent"},
        "spec": {
            "execution": {"mocking": {"enabled": True}},
            "working_memory": {"compaction": {"strategy": "keep_recent", "max_messages": 3}},
        },
    }
    _instantiate(manifest, tmp_path, monkeypatch)
    assert manifest["spec"]["context_manager"] == {"type": "stack", "params": {"max_messages": 3}}


def test_explicit_context_manager_is_left_untouched(tmp_path: Path, monkeypatch):
    manifest = {
        "metadata": {"name": "agent"},
        "spec": {
            "execution": {"mocking": {"enabled": True}},
            "context_manager": {"type": "sliding_window", "params": {"window_size": 9}},
            "working_memory": {"compaction": {"strategy": "keep_recent", "max_messages": 3}},
        },
    }
    _instantiate(manifest, tmp_path, monkeypatch)
    assert manifest["spec"]["context_manager"] == {"type": "sliding_window", "params": {"window_size": 9}}


def test_no_working_memory_compaction_leaves_context_manager_absent(tmp_path: Path, monkeypatch):
    manifest = {
        "metadata": {"name": "agent"},
        "spec": {"execution": {"mocking": {"enabled": True}}},
    }
    _instantiate(manifest, tmp_path, monkeypatch)
    assert "context_manager" not in manifest["spec"]


def test_summarize_wires_a_real_summarize_fn_off_the_resolved_engine(tmp_path: Path, monkeypatch):
    """standard:mock-llm still resolves to a LiveLlmEngine (pointed at a fake
    endpoint, not a SimulatedEngine) -- it has the completion primitives
    build_llm_summarize_fn needs, so summarize wires a real callable rather
    than degrading. The degrade-to-keep_recent path (no completion
    primitives available at all) is covered at the facade level in
    test_working_memory_compaction.py."""
    manifest = {
        "metadata": {"name": "agent"},
        "spec": {
            "execution": {"mocking": {"enabled": True}},
            "working_memory": {"compaction": {"strategy": "summarize", "keep_turns": 4}},
        },
    }
    _instantiate(manifest, tmp_path, monkeypatch)
    cm = manifest["spec"]["context_manager"]
    assert cm["type"] == "summarising"
    assert cm["params"]["keep_turns"] == 4
    assert callable(cm["params"]["summarize_fn"])
