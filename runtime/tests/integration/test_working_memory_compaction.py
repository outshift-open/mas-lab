#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""spec.working_memory.compaction facade over context_manager/CMFactory."""

import pytest
from mas.library.standard.plugins.context.conversation import (
    SlidingWindowConversation,
    StackConversation,
    SummarizingConversation,
)
from mas.runtime.boundary.context.working_memory_compaction import (
    apply_working_memory_compaction,
    build_llm_summarize_fn,
    context_manager_binding_from_compaction,
    resolve_working_memory_context_manager,
)
from mas.runtime.contracts.cm_factory import CMFactory


def test_keep_recent_translates_to_stack_type_and_max_messages():
    binding = context_manager_binding_from_compaction({"strategy": "keep_recent", "max_messages": 50})
    assert binding == {"type": "stack", "params": {"max_messages": 50}}


def test_default_strategy_is_keep_recent():
    binding = context_manager_binding_from_compaction({})
    assert binding["type"] == "stack"


def test_sliding_window_translates_window_size():
    binding = context_manager_binding_from_compaction({"strategy": "sliding_window", "window_size": 20})
    assert binding == {"type": "sliding_window", "params": {"window_size": 20}}


def test_summarize_translates_threshold_and_keep_turns():
    binding = context_manager_binding_from_compaction(
        {"strategy": "summarize", "summary_threshold": 8000, "keep_turns": 6}
    )
    assert binding == {
        "type": "summarising",
        "params": {"summary_threshold": 8000, "keep_turns": 6},
    }


def test_unknown_strategy_raises():
    with pytest.raises(ValueError, match="unknown working_memory.compaction.strategy"):
        context_manager_binding_from_compaction({"strategy": "bogus"})


def test_resolve_returns_none_without_working_memory():
    assert resolve_working_memory_context_manager({}) is None


def test_resolve_returns_none_without_compaction_block():
    assert resolve_working_memory_context_manager({"working_memory": {"persistent": True}}) is None


def test_explicit_context_manager_takes_precedence_over_compaction():
    spec = {
        "context_manager": {"type": "sliding_window", "params": {"window_size": 3}},
        "working_memory": {"compaction": {"strategy": "keep_recent", "max_messages": 999}},
    }
    assert resolve_working_memory_context_manager(spec) is None


def test_resolve_translates_compaction_when_no_explicit_context_manager():
    spec = {"working_memory": {"compaction": {"strategy": "sliding_window", "window_size": 7}}}
    binding = resolve_working_memory_context_manager(spec)
    assert binding == {"type": "sliding_window", "params": {"window_size": 7}}


class _FakeEngineNoModelAccess:
    api_key_env = "FAKE_API_KEY"

    def _uses_model_access(self):
        return False

    def _chat_completion(self, messages, *, api_key, tools, temperature):
        assert tools is None
        assert temperature == 0.0
        return {"role": "assistant", "content": f"summary of {len(messages)} prompt messages"}


class _FakeEngineModelAccess:
    def _uses_model_access(self):
        return True

    def _model_access_chat(self, messages, *, tools, temperature):
        assert tools is None
        return {"role": "assistant", "content": "summary via model access"}


def test_build_llm_summarize_fn_uses_chat_completion_path():
    fn = build_llm_summarize_fn(_FakeEngineNoModelAccess())
    result = fn([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])
    assert result == "summary of 2 prompt messages"


def test_build_llm_summarize_fn_uses_model_access_path():
    fn = build_llm_summarize_fn(_FakeEngineModelAccess())
    result = fn([{"role": "user", "content": "hi"}])
    assert result == "summary via model access"


def test_apply_working_memory_compaction_wires_a_real_context_manager():
    """End to end: the resolved binding actually instantiates via CMFactory
    and produces the expected ConversationStrategy behavior."""
    spec = {"working_memory": {"compaction": {"strategy": "keep_recent", "max_messages": 2}}}
    apply_working_memory_compaction(spec)
    assert spec["context_manager"] == {"type": "stack", "params": {"max_messages": 2}}

    cm = CMFactory.create(spec=spec["context_manager"])
    assert isinstance(cm, StackConversation)
    past = [{"role": "user", "content": f"m{i}"} for i in range(5)]
    assert len(cm.manage_history(past, 0)) == 2


def test_apply_working_memory_compaction_summarize_with_live_engine():
    spec = {"working_memory": {"compaction": {"strategy": "summarize", "keep_turns": 3}}}
    apply_working_memory_compaction(spec, engine=_FakeEngineNoModelAccess())

    cm_binding = spec["context_manager"]
    assert cm_binding["type"] == "summarising"
    assert callable(cm_binding["params"]["summarize_fn"])

    cm = CMFactory.create(spec=cm_binding)
    assert isinstance(cm, SummarizingConversation)


def test_apply_working_memory_compaction_summarize_without_engine_degrades_to_keep_recent():
    """No live LLM engine available -- must not crash; falls back safely."""
    spec = {"working_memory": {"compaction": {"strategy": "summarize"}}}
    apply_working_memory_compaction(spec, engine=None)
    assert spec["context_manager"] == {"type": "stack", "params": {}}


def test_apply_working_memory_compaction_noop_when_nothing_configured():
    spec = {"description": "an agent"}
    apply_working_memory_compaction(spec)
    assert "context_manager" not in spec


def test_sliding_window_binding_instantiates_via_registry():
    spec = {"working_memory": {"compaction": {"strategy": "sliding_window", "window_size": 4}}}
    apply_working_memory_compaction(spec)
    cm = CMFactory.create(spec=spec["context_manager"])
    assert isinstance(cm, SlidingWindowConversation)
    assert cm.max_turns == 4


class _FakeEngineWithBudget(_FakeEngineNoModelAccess):
    def __init__(self, *, max_llm_calls):
        from mas.runtime.boundary.gov.budget import BudgetTracker

        self._budget = BudgetTracker(max_llm_calls=max_llm_calls)


def test_build_llm_summarize_fn_counts_against_engine_budget():
    engine = _FakeEngineWithBudget(max_llm_calls=5)
    fn = build_llm_summarize_fn(engine)
    fn([{"role": "user", "content": "hi"}])
    assert engine._budget.llm_calls == 1


def test_build_llm_summarize_fn_raises_when_budget_exhausted():
    engine = _FakeEngineWithBudget(max_llm_calls=1)
    fn = build_llm_summarize_fn(engine)
    fn([{"role": "user", "content": "hi"}])
    with pytest.raises(RuntimeError, match="budget exceeded"):
        fn([{"role": "user", "content": "again"}])
