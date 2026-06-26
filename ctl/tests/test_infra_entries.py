#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for typed InfraBundle spec.entries[] resolution."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mas.ctl.infra.pipeline_chain import BidirectionalInfraPipeline, InfraChainContext
from mas.ctl.infra.resolve import _load_file, bidirectional_pipeline_for, resolve_infra_refs
from mas.ctl.workspace.config import WorkspaceConfig


def test_bidirectional_pipeline_forward_short_circuit():
    calls: list[str] = []

    def cache(ctx: InfraChainContext):
        calls.append(f"fwd:{ctx.entry_id}")
        return {"content": "cached"}

    def llm(ctx: InfraChainContext):
        calls.append(f"fwd:{ctx.entry_id}")
        return None

    pipe = BidirectionalInfraPipeline(
        forward_handlers=[("cache", cache), ("llm", llm)],
    )
    ctx = InfraChainContext(query={"messages": []})
    reply, handled = pipe.forward_query(ctx)
    assert handled is True
    assert reply == {"content": "cached"}
    assert calls == ["fwd:cache"]


def test_bidirectional_pipeline_backward_transform():
    def cache_reply(ctx: InfraChainContext):
        return {**ctx.query, "cached": True}

    pipe = BidirectionalInfraPipeline(
        forward_handlers=[("cache", lambda _c: None)],
        reply_handlers=[("cache", cache_reply)],
    )
    ctx = InfraChainContext(query={"messages": []}, correlation_id="abc")
    out = pipe.backward_reply(ctx, {"content": "hello"})
    assert out == {"content": "hello", "cached": True}


def test_bidirectional_pipeline_from_resolved_infra(tmp_path: Path):
    infra = resolve_infra_refs(["standard:mock-llm"], anchor=tmp_path)
    pipe = bidirectional_pipeline_for(infra.llm_proxy)
    assert isinstance(pipe, BidirectionalInfraPipeline)
    ctx = InfraChainContext(query={"messages": [{"role": "user", "content": "hi"}]})
    reply, handled = pipe.forward_query(ctx)
    assert handled is False
    assert reply is None


def test_infra_bundle_entries_loads_llm_proxy_cached(tmp_path: Path, monkeypatch):
    bundle = Path(__file__).resolve().parents[2] / (
        "library-standard/src/mas/library/standard/libs/standard/llm-proxy-cached.yaml"
    )
    if not bundle.is_file():
        pytest.skip("library-standard bundle not in workspace")

    ws = WorkspaceConfig.load(tmp_path)
    merged = _load_file(bundle, workspace=ws)
    assert merged.kind == "InfraBundle"
    pipeline = merged.pipeline or []
    assert any(step.get("middleware") == "llm_cache" for step in pipeline)
    assert merged.proxy.api_base or merged.models.default_llm is not None or merged.name


def test_workspace_infra_refs_resolve_from_subdirectory():
    """Refs like ``standard:openai`` resolve from mas-workspace root, not anchor only."""
    repo = Path(__file__).resolve().parents[2]
    tutorial = repo / "docs/tutorials/01-building-an-agent"
    sample = repo / "examples" / "sample-workspace"
    if not (sample / "mas-workspace.yaml").is_file():
        pytest.skip("examples/sample-workspace/mas-workspace.yaml not in workspace")
    ws = WorkspaceConfig.load(sample)
    assert ws.found
    infra = resolve_infra_refs(
        ["standard:openai"],
        anchor=tutorial,
        workspace=ws,
    )
    assert infra.llm_proxy.get("api_base")
