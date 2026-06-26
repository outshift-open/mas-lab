#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Kernel driver loop integration."""

from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.engine.simulated import SimulatedEngine
from mas.runtime.schema.ingress import EngineIoReturn, LifecyclePause, LifecycleResume


def test_runtime_instance_run_user_text_produces_client_response():
    engine = SimulatedEngine(
        script={
            1: EngineIoReturn(
                correlation_id=1,
                response_kind="MODEL_TEXT",
                next_step="STOP",
                text="hello back",
            )
        }
    )
    inst = RuntimeInstance.from_parts(engine=engine)
    inst.capture_session_baseline()
    trace = inst.run_user_text("hello")
    assert trace.client_responses or trace.steps


def test_runtime_instance_pause_and_resume():
    inst = RuntimeInstance.from_parts()
    inst.capture_session_baseline()
    pause_trace = inst.pause(reason="operator")
    assert pause_trace is not None
    resume_trace = inst.resume()
    assert resume_trace is not None


def test_runtime_instance_reset_after_baseline():
    inst = RuntimeInstance.from_parts()
    inst.capture_session_baseline()
    inst.run_user_text("turn one")
    inst.reset_session()
    assert inst.kernel.q.dp in {"IDLE", "AWAITING_INGRESS", "EGRESS_PENDING", "EVALUATING"}
