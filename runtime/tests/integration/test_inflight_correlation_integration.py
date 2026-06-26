#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Inflight correlation tracking integration."""

from mas.runtime.kernel.inflight import (
    dismiss_inflight,
    is_inflight,
    pending_for_validate,
    register_inflight,
)
from mas.runtime.kernel.state import QProduct


def test_inflight_parallel_tool_correlations():
    q = QProduct()
    register_inflight(q, 1)
    register_inflight(q, 2)
    assert is_inflight(q, 1)
    assert pending_for_validate(q) == [1, 2]
    dismiss_inflight(q, 1)
    assert pending_for_validate(q) == [2]
