#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""δ is specified as a function; Python mutates in place. Isolation is snapshot."""

from __future__ import annotations

import copy

from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.kernel.types import LifecycleState
from mas.runtime.session.cow import capture_kernel, restore_kernel


def test_in_place_mutation_is_the_implementation_of_functional_delta() -> None:
    """q ← δ(q, σ) is specified as a function. The live object mutates.

    A snapshot is a copy of q at a governance cut. Restoring it is the
    functional reading: later writes to the live product do not leak into
    the frozen node. This is not a rewrite of every ``q.dp =`` assignment.
    """
    kernel = RuntimeKernel()
    before = capture_kernel(kernel)
    live_q = kernel.q
    kernel.q.ctrl = LifecycleState.STOPPED
    kernel.q.cot_pass = 4
    assert live_q.ctrl is LifecycleState.STOPPED
    assert before.q.ctrl is LifecycleState.RUNNING
    assert before.q.cot_pass == 0
    restored = copy.deepcopy(before.q)
    assert restored.ctrl is LifecycleState.RUNNING
    restore_kernel(kernel, before)
    assert kernel.q.ctrl is LifecycleState.RUNNING
    assert kernel.q.cot_pass == 0
    kernel.q.cot_pass = 9
    assert before.q.cot_pass == 0
