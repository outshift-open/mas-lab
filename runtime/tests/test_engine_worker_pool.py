#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""EngineWorkerPool — batch queue depth and manifest wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mas.ctl.manifest.spec_bindings import SpecBindingError, parse_execution
from mas.runtime.driver.driver import KernelDriver
from mas.runtime.engine.worker_pool import DEFAULT_ENGINE_QUEUE_DEPTH, EngineWorkerPool
from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.spec.parser import parse_agent_spec


def test_default_queue_depth_constant():
    assert DEFAULT_ENGINE_QUEUE_DEPTH == 32


def test_submit_rejects_when_queue_full():
    pool = EngineWorkerPool(worker=MagicMock(), max_depth=2)
    pool.submit(InvokeEngineIo(correlation_id=1, op="TOOL_CALL"))
    pool.submit(InvokeEngineIo(correlation_id=2, op="TOOL_CALL"))
    with pytest.raises(RuntimeError, match="engine outbound queue full"):
        pool.submit(InvokeEngineIo(correlation_id=3, op="TOOL_CALL"))


def test_parse_agent_spec_reads_engine_queue_depth():
    config, _ = parse_agent_spec({"execution": {"engine_queue_depth": 64}})
    assert config.engine_queue_depth == 64


def test_parse_agent_spec_default_engine_queue_depth():
    config, _ = parse_agent_spec({})
    assert config.engine_queue_depth == DEFAULT_ENGINE_QUEUE_DEPTH


def test_parse_execution_validates_engine_queue_depth():
    parse_execution({"engine_queue_depth": 16})
    with pytest.raises(SpecBindingError, match="engine_queue_depth"):
        parse_execution({"engine_queue_depth": 0})


def test_driver_engine_pool_uses_kernel_config_depth():
    kernel = RuntimeKernel(config=KernelConfig(engine_queue_depth=12))
    driver = KernelDriver(kernel=kernel, engine=MagicMock())
    assert driver.engine_pool is not None
    assert driver.engine_pool.max_depth == 12
