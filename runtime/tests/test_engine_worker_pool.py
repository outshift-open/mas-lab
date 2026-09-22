#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""EngineWorkerPool — batch queue depth and manifest wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mas.runtime.driver.driver import DEFAULT_MAX_AUTO_STEPS, KernelDriver
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.engine.worker_pool import DEFAULT_ENGINE_QUEUE_DEPTH, EngineWorkerPool
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn
from mas.runtime.spec.parser import parse_agent_spec


def test_default_queue_depth_constant():
    assert DEFAULT_ENGINE_QUEUE_DEPTH == 32


def test_process_one_returns_error_when_worker_raises() -> None:
    def _boom(io: InvokeEngineIo) -> EngineIoReturn:
        raise RuntimeError("worker exploded")

    pool = EngineWorkerPool(worker=_boom)
    pool.submit(InvokeEngineIo(correlation_id=7, op="TOOL_CALL"))
    result = pool.process_one()
    assert result is not None
    assert result.response_kind == "ERROR"
    assert result.next_step == "STOP"
    assert result.correlation_id == 7
    assert "worker exploded" in result.text
    assert pool.pop_inbound() is result


def test_submit_rejects_when_queue_full():
    pool = EngineWorkerPool(worker=MagicMock(), max_depth=2)
    pool.submit(InvokeEngineIo(correlation_id=1, op="TOOL_CALL"))
    pool.submit(InvokeEngineIo(correlation_id=2, op="TOOL_CALL"))
    with pytest.raises(RuntimeError, match="engine outbound queue full"):
        pool.submit(InvokeEngineIo(correlation_id=3, op="TOOL_CALL"))


def test_parse_agent_spec_reads_engine_queue_depth():
    config, _ = parse_agent_spec({}, runtime_engine={"engine_queue_depth": 64})
    assert config.engine_queue_depth == 64


def test_parse_agent_spec_default_engine_queue_depth():
    config, _ = parse_agent_spec({})
    assert config.engine_queue_depth == DEFAULT_ENGINE_QUEUE_DEPTH


def test_driver_engine_pool_uses_kernel_config_depth():
    kernel = RuntimeKernel(config=KernelConfig(engine_queue_depth=12))
    driver = KernelDriver(kernel=kernel, engine=MagicMock())
    assert driver.engine_pool is not None
    assert driver.engine_pool.max_depth == 12


def test_default_max_auto_steps_constant():
    assert DEFAULT_MAX_AUTO_STEPS == 512


def test_parse_agent_spec_reads_max_auto_steps():
    config, _ = parse_agent_spec({}, runtime_engine={"max_auto_steps": 20})
    assert config.max_auto_steps == 20


def test_parse_agent_spec_default_max_auto_steps():
    config, _ = parse_agent_spec({})
    assert config.max_auto_steps == DEFAULT_MAX_AUTO_STEPS


def test_runtime_instance_threads_kernel_config_max_auto_steps_to_driver():
    instance = RuntimeInstance.from_parts(config=KernelConfig(max_auto_steps=7))
    assert instance.driver.max_auto_steps == 7
