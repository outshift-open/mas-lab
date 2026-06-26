#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Context assembly integration."""

from types import SimpleNamespace

from mas.runtime.boundary.context.assemble import assemble_llm_messages, has_tool_results
from mas.runtime.boundary.context.working_memory import WorkingMemoryStore


def test_assemble_llm_messages_includes_user_turn():
    ctx = SimpleNamespace(
        working_memory=WorkingMemoryStore(),
        injected_context=[],
        memory_seeds=[],
        committed_messages=[],
        turn_history=[],
        last_user_text="hello",
        observability=None,
        turn_index=0,
        agent_id="agent",
    )
    messages = assemble_llm_messages(
        ctx,
        manifest={"spec": {"context_manager": {"type": "stack"}}},
    )
    assert any(m.get("role") == "user" and m.get("content") == "hello" for m in messages)


def test_has_tool_results_detects_tool_role():
    assert has_tool_results([{"role": "tool", "content": "x"}])
    assert not has_tool_results([{"role": "user", "content": "x"}])
