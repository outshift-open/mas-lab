#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Parallel tool dispatch — driver batch integrity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mas.runtime.driver.driver import DriverTrace, KernelDriver
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.schema.egress import InvokeEngineIo
from mas.runtime.schema.ingress import EngineIoReturn


def test_parallel_tool_dispatch_strict_zip_raises_on_length_mismatch():
    """Engine pool must return one result per submitted InvokeEngineIo."""
    kernel = RuntimeKernel()
    driver = KernelDriver(kernel=kernel, engine=MagicMock())
    pool = MagicMock()
    pool.submit = MagicMock()
    pool.drain.return_value = [
        EngineIoReturn(
            correlation_id=1,
            response_kind="TOOL_RESULT",
            next_step="STOP",
            text="only one result",
        ),
    ]
    driver.engine_pool = pool

    ios = [
        InvokeEngineIo(correlation_id=1, op="TOOL_CALL"),
        InvokeEngineIo(correlation_id=2, op="TOOL_CALL"),
    ]

    with pytest.raises(ValueError, match="zip"):
        driver._dispatch_engine_batch(ios, DriverTrace())
