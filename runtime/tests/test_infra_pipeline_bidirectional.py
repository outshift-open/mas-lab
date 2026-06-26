#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for bidirectional infra pipeline engine wrapping."""
from __future__ import annotations

from dataclasses import dataclass

from mas.runtime.engine.infra_pipeline import (
    BidirectionalPipelineEngine,
    LlmCacheMiddleware,
    wrap_bidirectional_pipeline,
)
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


@dataclass
class _EchoEngine:
    def exchange_preview(self, op: str) -> str:
        return f"echo:{op}"

    def invoke(self, io: InvokeEngineIo) -> EngineIoReturn:
        return EngineIoReturn(
            correlation_id=io.correlation_id,
            response_kind="MODEL_TEXT",
            next_step="STOP",
            text="live-response",
        )


def test_wrap_bidirectional_pipeline_uses_cache(tmp_path):
    cache_path = tmp_path / "cache.json"
    pipeline = [{"middleware": "llm_cache", "params": {"cache_path": str(cache_path)}}]
    engine = wrap_bidirectional_pipeline(_EchoEngine(), pipeline)

    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    first = engine.invoke(io)
    assert first.text == "live-response"

    second = engine.invoke(io)
    assert second.text == "live-response"
    assert cache_path.is_file()


def test_bidirectional_engine_backward_reply_passthrough():
    inner = LlmCacheMiddleware(inner=_EchoEngine(), enabled=False)
    facade = BidirectionalPipelineEngine(inner=inner, pipeline_steps=[])
    io = InvokeEngineIo(correlation_id=2, op="LLM_CALL")
    ret = facade.invoke(io)
    assert ret.text == "live-response"
