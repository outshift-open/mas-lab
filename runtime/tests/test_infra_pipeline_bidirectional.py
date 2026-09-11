#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for bidirectional infra pipeline engine wrapping."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from mas.runtime.engine.infra_pipeline import (
    BidirectionalPipelineEngine,
    LlmCacheMiddleware,
    apply_middleware,
    wrap_bidirectional_pipeline,
)
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


@dataclass
class _EchoEngine:
    preview_text: str = "echo:LLM_CALL"
    calls: int = 0

    def exchange_preview(self, op: str) -> str:
        return self.preview_text if op == "LLM_CALL" else f"echo:{op}"

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        self.calls += 1
        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="MODEL_TEXT",
            next_step="STOP",
            text=f"live-response-{self.calls}",
        )


def test_wrap_bidirectional_pipeline_uses_cache(tmp_path):
    cache_path = tmp_path / "cache.json"
    pipeline = [{"middleware": "llm_cache", "params": {"cache_path": str(cache_path)}}]
    inner = _EchoEngine()
    engine = wrap_bidirectional_pipeline(inner, pipeline)

    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    first = engine.invoke(io)
    assert first.text == "live-response-1"
    assert inner.calls == 1

    second = engine.invoke(io)
    assert second.text == "live-response-1"
    assert inner.calls == 1
    assert cache_path.is_file()


def test_bidirectional_engine_backward_reply_passthrough():
    echo = _EchoEngine()
    inner = LlmCacheMiddleware(inner=echo, allow_read=False, allow_write=False)
    facade = BidirectionalPipelineEngine(inner=inner, pipeline_steps=[])
    io = InvokeEngineIo(correlation_id=2, op="LLM_CALL")
    ret = facade.invoke(io)
    assert ret.text == "live-response-1"


def test_llm_cache_raise_on_miss(tmp_path):
    cache_path = tmp_path / "cache.json"
    engine = apply_middleware(
        _EchoEngine(),
        {
            "middleware": "llm_cache",
            "params": {"cache_path": str(cache_path), "raise_on_miss": True},
        },
    )
    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    with pytest.raises(RuntimeError, match="llm_cache miss"):
        engine.invoke(io)


def test_llm_cache_read_only_skips_write(tmp_path):
    cache_path = tmp_path / "cache.json"
    inner = _EchoEngine()
    engine = apply_middleware(
        inner,
        {
            "middleware": "llm_cache",
            "params": {"cache_path": str(cache_path), "allow_write": False},
        },
    )
    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    engine.invoke(io)
    assert inner.calls == 1
    engine.invoke(io)
    assert inner.calls == 2
    assert not cache_path.exists()


def test_llm_cache_write_only_skips_read(tmp_path):
    cache_path = tmp_path / "cache.json"
    inner = _EchoEngine()
    engine = apply_middleware(
        inner,
        {
            "middleware": "llm_cache",
            "params": {"cache_path": str(cache_path), "allow_read": False, "allow_write": True},
        },
    )
    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    engine.invoke(io)
    engine.invoke(io)
    assert inner.calls == 2


def test_llm_cache_caches_post_tool_preview(tmp_path):
    cache_path = tmp_path / "cache.json"
    inner = _EchoEngine(preview_text="history [tool call_id=call_1] result")
    engine = apply_middleware(
        inner,
        {"middleware": "llm_cache", "params": {"cache_path": str(cache_path)}},
    )
    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    first = engine.invoke(io)
    second = engine.invoke(io)
    assert first.text == "live-response-1"
    assert second.text == "live-response-1"
    assert inner.calls == 1
