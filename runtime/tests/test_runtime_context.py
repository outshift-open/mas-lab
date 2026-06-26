#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runtime binding context isolation across concurrent feeds."""

from __future__ import annotations

from mas.runtime.boundary.gov.telemetry import get_bound_observability
from mas.runtime.driver.driver import KernelDriver
from mas.runtime.kernel.coord_hook import get_coordination
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.schema.ingress import UserInputReceived


def test_runtime_binding_cleared_after_feed():
    kernel = RuntimeKernel()
    driver = KernelDriver(kernel=kernel, coordination=None, observability=None)

    assert get_coordination() is None
    assert get_bound_observability() is None

    driver.feed(UserInputReceived(user_turn_id="u1", text="hi"))

    assert get_coordination() is None
    assert get_bound_observability() is None
