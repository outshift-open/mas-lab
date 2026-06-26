#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Working memory store integration."""

from mas.runtime.boundary.context.working_memory import WorkingMemoryStore


def test_working_memory_tool_call_round_trip():
    store = WorkingMemoryStore()
    store.record_assistant_tool_call(call_id="c1", tool_name="calc", arguments={"x": 1})
    store.record_tool_result(call_id="c1", content="42")
    roles = [m["role"] for m in store.messages]
    assert roles == ["assistant", "tool"]


def test_working_memory_clear_resets_open_call():
    store = WorkingMemoryStore()
    store.record_assistant_tool_call(call_id="c1", tool_name="t", arguments={})
    store.clear()
    assert store.messages == []
