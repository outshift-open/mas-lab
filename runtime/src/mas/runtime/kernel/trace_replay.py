#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Replay hand-curated TLC-aligned trace fixtures against the Python kernel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from mas.runtime.kernel.config import KernelConfig
from mas.runtime.kernel.orchestrator import RuntimeKernel
from mas.runtime.schema.governance import GovPolicyProfile
from mas.runtime.schema.ingress import IngressSymbol

_INGRESS_ADAPTER: TypeAdapter[IngressSymbol] = TypeAdapter(IngressSymbol)


def _parse_ingress(raw: dict[str, Any]) -> IngressSymbol:
    return _INGRESS_ADAPTER.validate_python(raw)


def replay_trace(trace: dict[str, Any]) -> RuntimeKernel:
    profile_name = trace.get("gov_policy_profile", "BLOCK_DESTRUCTIVE")
    config = KernelConfig(
        pattern_plugin_id=trace.get("pattern_plugin_id", "react@v1"),
        gov_policy_profile=GovPolicyProfile(profile_name),
        gov_block_destructive=trace.get("gov_block_destructive", False),
        gov_trigger_destructive=trace.get("gov_trigger_destructive", False),
        hitl_on_tool=trace.get("hitl_on_tool", False),
        enable_memory_egress=trace.get("enable_memory_egress", False),
        enable_transport_egress=trace.get("enable_transport_egress", False),
    )
    kernel = RuntimeKernel(config=config)
    for step in trace.get("steps", []):
        result_egress: list = []
        ingress_raw = step.get("ingress")
        if ingress_raw is not None:
            event = _parse_ingress(ingress_raw)
            result = kernel.transition(event)
            result_egress = result.egress

        name = trace.get("name", "trace")
        if expect_dp := step.get("expect_dp"):
            assert kernel.q.dp.value == expect_dp, (
                f"{name}: expected dp={expect_dp}, got {kernel.q.dp.value}"
            )
        if expect_ctrl := step.get("expect_ctrl"):
            assert kernel.q.ctrl.value == expect_ctrl
        if expect_scheduled := step.get("expect_scheduled"):
            assert kernel.q.scheduled_egress == expect_scheduled
        if expect_inflight := step.get("expect_inflight"):
            assert kernel.q.inflight_kind == expect_inflight
        if expect_tool := step.get("expect_tool"):
            assert kernel.q.tool.value == expect_tool
        if expect_gov := step.get("expect_gov"):
            assert kernel.q.gov_state == expect_gov
        if expect_memory := step.get("expect_memory"):
            assert kernel.q.memory.value == expect_memory
        if expect_transport := step.get("expect_transport"):
            assert kernel.q.transport.value == expect_transport
        if expect_egress_kind := step.get("expect_egress_kind"):
            assert any(e.kind.value == expect_egress_kind for e in result_egress), (
                f"{name}: missing egress {expect_egress_kind}"
            )
        if expect_tau_len := step.get("expect_tau_len"):
            assert len(kernel.run.records) == expect_tau_len
    return kernel


def load_fixture(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def replay_fixture_file(path: Path) -> None:
    for trace in load_fixture(path):
        replay_trace(trace)
