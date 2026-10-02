#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.kernel.types import LifecycleState
from mas.runtime.schema.ingress import UserInputReceived
from mas.runtime.session.cow import capture_kernel, freeze, is_frozen


def test_capture_kernel_is_isolated_from_later_mutation() -> None:
    kernel = RuntimeKernel()
    cow = capture_kernel(kernel)
    kernel.q.ctrl = LifecycleState.STOPPED
    kernel.q.cot_pass = 9
    assert cow.q.ctrl == LifecycleState.RUNNING
    assert cow.q.cot_pass == 0
    assert is_frozen(cow.q)
    assert not is_frozen(kernel.q)


def test_freeze_then_transition_clones_live_kernel() -> None:
    kernel = RuntimeKernel()
    freeze(kernel.q)
    freeze(kernel.run)
    original = kernel.q
    kernel.transition(UserInputReceived(user_turn_id="u1", text="hi"))
    assert kernel.q is not original
    assert not is_frozen(kernel.q)
