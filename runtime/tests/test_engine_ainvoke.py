#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Parity between EngineContract.invoke and ainvoke."""

from __future__ import annotations

import pytest

from mas.runtime.engine.llm_live import LiveLlmEngine
from mas.runtime.engine.simulated import SimulatedEngine
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


class _StubProvider:
    kind = "openai"

    def __init__(self, message: dict) -> None:
        self.message = message
        self.sync_calls = 0
        self.async_calls = 0

    def chat_completion(self, **kwargs):
        self.sync_calls += 1
        self.last_kwargs = kwargs
        return dict(self.message)

    async def achat_completion(self, **kwargs):
        self.async_calls += 1
        self.last_kwargs = kwargs
        return dict(self.message)


@pytest.mark.asyncio
async def test_simulated_engine_ainvoke_matches_invoke():
    engine = SimulatedEngine(stop_text="hello")
    io = InvokeEngineIo(correlation_id=2, op="LLM_CALL")
    sync = engine.invoke(io)
    async_ret = await engine.ainvoke(io)
    assert sync == async_ret
    assert async_ret.text == "hello"


@pytest.mark.asyncio
async def test_live_engine_ainvoke_parity_with_invoke():
    message = {"role": "assistant", "content": "same-answer", "finish_reason": "stop"}
    provider = _StubProvider(message)
    engine = LiveLlmEngine(llm_provider=provider, use_cache=False, model="stub")
    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    sync = engine.invoke(io)
    async_ret = await engine.ainvoke(io)
    assert sync.text == async_ret.text == "same-answer"
    assert provider.sync_calls == 1
    assert provider.async_calls == 1


@pytest.mark.asyncio
async def test_live_engine_ainvoke_rejects_provider_without_achat_completion():
    class SyncOnly:
        kind = "openai"

        def chat_completion(self, **kwargs):
            return {"content": "nope"}

    engine = LiveLlmEngine(llm_provider=SyncOnly(), use_cache=False, model="stub")
    ret = await engine.ainvoke(InvokeEngineIo(correlation_id=1, op="LLM_CALL"))
    assert ret.response_kind == "ERROR"
    assert "achat_completion" in (ret.text or "")
