#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for typed InfraBundle spec.entries[] resolution."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mas.ctl.infra.pipeline_chain import BidirectionalInfraPipeline, InfraChainContext
from mas.ctl.infra.resolve import (
    InfraResolveError,
    _load_file,
    bidirectional_pipeline_for,
    resolve_infra_refs,
)
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


def test_relative_llm_cache_path_is_resolved_from_infra_manifest_dir(tmp_path: Path):
    infra_dir = tmp_path / "infra"
    infra_dir.mkdir()
    (infra_dir / "llm-cache-write.yaml").write_text(
        """
apiVersion: infra/v1
kind: InfraMiddleware
metadata:
  name: llm-cache-write
spec:
  middleware: llm_cache
  applies_to: [LLM_CALL]
  params:
    allow_read: true
    allow_write: true
    cache_path: .cache/demo-cache.json
""".strip(),
        encoding="utf-8",
    )

    infra = resolve_infra_refs(["infra/llm-cache-write.yaml"], anchor=tmp_path)
    pipeline = infra.llm_proxy.get("pipeline") or []
    assert pipeline
    params = pipeline[0]["params"]
    assert Path(params["cache_path"]).is_absolute()
    assert Path(params["cache_path"]) == (infra_dir / ".cache" / "demo-cache.json").resolve()


def test_relative_ref_resolves_from_anchor_not_process_cwd(tmp_path: Path, monkeypatch):
    """A same-named file in the process CWD must never shadow the anchor-relative ref."""
    project_dir = tmp_path / "anchor-project"
    infra_dir = project_dir / "infra"
    infra_dir.mkdir(parents=True)
    (infra_dir / "llm-cache-write.yaml").write_text(
        """
apiVersion: infra/v1
kind: InfraMiddleware
metadata:
  name: llm-cache-write
spec:
  middleware: llm_cache
  applies_to: [LLM_CALL]
  params:
    cache_path: .cache/from-anchor.json
""".strip(),
        encoding="utf-8",
    )

    decoy_dir = tmp_path / "decoy-cwd"
    decoy_infra_dir = decoy_dir / "infra"
    decoy_infra_dir.mkdir(parents=True)
    (decoy_infra_dir / "llm-cache-write.yaml").write_text(
        """
apiVersion: infra/v1
kind: InfraMiddleware
metadata:
  name: llm-cache-write
spec:
  middleware: llm_cache
  applies_to: [LLM_CALL]
  params:
    cache_path: .cache/from-decoy-cwd.json
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.chdir(decoy_dir)
    infra = resolve_infra_refs(["infra/llm-cache-write.yaml"], anchor=project_dir)
    pipeline = infra.llm_proxy.get("pipeline") or []
    assert pipeline
    cache_path = Path(pipeline[0]["params"]["cache_path"])
    assert cache_path == (infra_dir / ".cache" / "from-anchor.json").resolve()
    assert "from-decoy-cwd" not in cache_path.as_posix()


def test_relative_ref_not_loaded_from_process_cwd_only(tmp_path: Path, monkeypatch):
    """Process CWD must not satisfy a ref that is missing under anchor."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    decoy = tmp_path / "decoy"
    decoy_infra = decoy / "infra"
    decoy_infra.mkdir(parents=True)
    (decoy_infra / "missing-at-anchor.yaml").write_text(
        """
apiVersion: infra/v1
kind: InfraMiddleware
metadata:
  name: decoy
spec:
  middleware: llm_cache
  applies_to: [LLM_CALL]
  params:
    cache_path: .cache/decoy.json
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(decoy)
    with pytest.raises((FileNotFoundError, InfraResolveError)):
        resolve_infra_refs(["infra/missing-at-anchor.yaml"], anchor=project_dir)


def test_library_samples_llm_cache_write_resolves_cache_path():
    repo = Path(__file__).resolve().parents[2]
    manifest = repo / "library-samples" / "infra" / "llm-cache-write.yaml"
    if not manifest.is_file():
        pytest.skip("library-samples/infra/llm-cache-write.yaml not in workspace")
    infra = resolve_infra_refs(["library-samples/infra/llm-cache-write.yaml"], anchor=repo)
    pipeline = infra.llm_proxy.get("pipeline") or []
    assert pipeline and pipeline[0].get("middleware") == "llm_cache"
    cache_path = Path(pipeline[0]["params"]["cache_path"])
    expected = (repo / "library-samples" / "infra" / "cache" / "demo.llm-cache.json").resolve()
    assert cache_path == expected


def test_resolve_infra_uses_workspace_root_when_anchor_omitted():
    """Library/eval paths that pass workspace= only still resolve scheme refs."""
    repo = Path(__file__).resolve().parents[2]
    sample = repo / "library-samples" / "sample-workspace"
    if not (sample / "config.yaml").is_file():
        pytest.skip("library-samples/sample-workspace/config.yaml not in workspace")
    ws = WorkspaceConfig.load(sample)
    assert ws.found and ws.root
    infra = resolve_infra_refs(["standard:mock-llm"], workspace=ws)
    assert infra.refs == ["standard:mock-llm"]
    assert infra.llm_proxy.get("api_key_env")


def test_workspace_infra_refs_resolve_from_subdirectory():
    """Refs like ``standard:openai`` resolve from config root, not anchor only."""
    repo = Path(__file__).resolve().parents[2]
    tutorial = repo / "docs/tutorials/01-building-an-agent"
    sample = repo / "library-samples" / "sample-workspace"
    if not (sample / "config.yaml").is_file():
        pytest.skip("library-samples/sample-workspace/config.yaml not in workspace")
    ws = WorkspaceConfig.load(sample)
    assert ws.found
    infra = resolve_infra_refs(
        ["standard:openai"],
        anchor=tutorial,
        workspace=ws,
    )
    assert infra.llm_proxy.get("api_base")
