#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Registry / category-mapping tests — do not require the OTel SDK."""

from __future__ import annotations

from mas.library.telemetry.conversion.envelope import (
    KIND_ENVELOPE,
    export_layer_for_kind,
)
from mas.library.telemetry.conversion.mappings.base import (
    build_handler_table,
    register,
    registered_kinds,
)

# The full set of event kinds the OSS converter handled (parity contract).
_OSS_KINDS = {
    "mas_call_start",
    "mas_call_end",
    "execution_start",
    "execution_end",
    "infrastructure_info",
    "processing_call_start",
    "processing_call_end",
    "context_assembled",
    "context_part_contributed",
    "llm_call_start",
    "llm_call_end",
    "tool_call_start",
    "tool_call_end",
    "workflow_transition_start",
    "workflow_transition_end",
    "memory_store_start",
    "memory_store_end",
    "memory_read_start",
    "memory_read_end",
    "memory_retrieve_start",
    "memory_retrieve_end",
    "memory_call_start",
    "memory_call_end",
    "rag_query_start",
    "rag_query_end",
    "agent_communication_start",
    "agent_communication_end",
    "skill_execution_start",
    "skill_execution_end",
    "governance_event",
    "governance_checked",
    "governance_policy",
    "hitl_request",
    "policy_denial",
    "policy_allow",
    "hitl_gate",
    "budget_event",
    "control_intervention",
    "transformation_event",
    "governance_denied",
    "routing",
    "routing_result",
    "user_input",
    "user_output",
    "client_response",
    "compaction",
    "parallel_group_start",
    "parallel_group_end",
    "parallel_group_merge",
    "network_call_start",
    "network_call_end",
    "state_update_start",
    "state_update_end",
}


def test_all_oss_kinds_registered():
    kinds = set(registered_kinds())
    assert _OSS_KINDS <= kinds, f"missing handlers: {_OSS_KINDS - kinds}"


def test_handler_table_is_a_copy():
    t1 = build_handler_table()
    t1["_junk"] = None
    t2 = build_handler_table()
    assert "_junk" not in t2  # build returns a fresh dict each call


def test_register_new_kind():
    @register("unit_test_custom_kind")
    def _h(conv, ev):  # pragma: no cover - not invoked here
        pass

    assert "unit_test_custom_kind" in build_handler_table()


def test_every_registered_kind_has_an_envelope_or_governance_fallback():
    # Every built-in kind should be categorisable (either explicit envelope row,
    # or routed via the governance layer fallback / obs_wrap prefix at runtime).
    for kind in _OSS_KINDS:
        assert kind in KIND_ENVELOPE, f"{kind} missing from KIND_ENVELOPE"


def test_export_layer_mapping():
    assert export_layer_for_kind("llm_call_start") == "execution"
    assert export_layer_for_kind("mas_call_start") == "structure"
    assert export_layer_for_kind("context_assembled") == "semantic"
    assert export_layer_for_kind("governance_checked") == "governance"
    assert export_layer_for_kind("parallel_group_start") == "provenance"
    assert export_layer_for_kind("totally_unknown_kind") is None
