#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import asyncio

import pytest

from mas.runtime.driver.driver import KernelDriver
from mas.runtime.engine.inflight_llm import has_inflight
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.schema.egress import InvokeEngineIo


class _HangEngine:
    async def ainvoke(self, io):
        await asyncio.sleep(30)
        raise AssertionError("should have been cancelled")


@pytest.mark.asyncio
async def test_cancel_inflight_llm_returns_cancelled_finish_reason() -> None:
    driver = KernelDriver(kernel=RuntimeKernel(), engine=_HangEngine(), session_id="s-cancel")
    io = InvokeEngineIo(correlation_id=1, op="LLM_CALL")
    task = asyncio.create_task(driver._ainvoke_engine(io))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if has_inflight("s-cancel"):
            break
    assert has_inflight("s-cancel")
    from mas.runtime.engine.inflight_llm import cancel

    assert cancel("s-cancel") is True
    ret = await asyncio.wait_for(task, timeout=2)
    assert ret.finish_reason == "cancelled"
    assert ret.response_kind == "ERROR"
    assert has_inflight("s-cancel") is False
