#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from mas.library.standard.plugins.context.conversation import SummarizingConversation
from mas.library.standard.plugins.context.summarizer import DropSummarizer, LlmSummarizer
from mas.runtime.contracts.cm_factory import CMFactory
from mas.runtime.registry import get_registry


class _Engine:
    def summarize_messages(self, messages):
        return f"sum:{len(messages)}"


def test_summarizer_plugins_are_registered() -> None:
    reg = get_registry()
    assert reg.resolve_by_type("summarizer", "llm") is not None
    assert reg.resolve_by_type("summarizer", "drop") is not None
    assert isinstance(reg.create("summarizer", {"type": "llm"}), LlmSummarizer)
    assert isinstance(reg.create("summarizer", {"type": "drop"}), DropSummarizer)


def test_drop_summarizer_keeps_recent_turns() -> None:
    cm = CMFactory.create(
        spec={"type": "summarising", "params": {"keep_turns": 1, "summarizer": "drop"}},
    )
    past = [
        {"role": "user", "content": "old " + "x" * 80},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "new"},
        {"role": "assistant", "content": "b"},
    ]
    out = cm.manage_history(past, budget_tokens=1)
    assert [m["content"] for m in out] == ["new", "b"]


def test_llm_summarizer_uses_engine() -> None:
    cm = CMFactory.create(
        spec={"type": "summarising", "params": {"keep_turns": 1, "summarizer": "llm"}},
        engine=_Engine(),
    )
    past = [
        {"role": "user", "content": "old " + "x" * 80},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "new"},
        {"role": "assistant", "content": "b"},
    ]
    out = cm.manage_history(past, budget_tokens=1)
    assert out[0]["role"] == "system"
    assert "sum:" in out[0]["content"]
    assert out[-1]["content"] == "b"


def test_llm_summarizer_without_engine_drops(caplog: pytest.LogCaptureFixture) -> None:
    cm = CMFactory.create(
        spec={"type": "summarising", "params": {"keep_turns": 1, "hysteresis_ratio": 0}},
    )
    assert isinstance(cm, SummarizingConversation)
    past = [
        {"role": "user", "content": "old " + "x" * 80},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "new"},
    ]
    with caplog.at_level("WARNING"):
        out = cm.manage_history(past, budget_tokens=1)
    assert [m["role"] for m in out] == ["user"]
    assert out[0]["content"] == "new"
    assert any("no engine" in rec.message for rec in caplog.records)


def test_summarizer_string_shorthand_and_object_form() -> None:
    drop = CMFactory.create(
        spec={"type": "summarising", "params": {"summarizer": {"type": "drop"}}},
    )
    assert drop._summarizer.__class__.__name__ == "DropSummarizer"


def test_llm_summarizer_wraps_engine_prompt() -> None:
    from mas.library.standard.plugins.context.summarizer import SUMMARIZE_INSTRUCTIONS

    seen: list[list[dict]] = []

    class _RawEngine:
        def summarize_messages(self, messages):
            seen.append(messages)
            return "ok"

    plugin = LlmSummarizer()
    plugin.bind_engine(_RawEngine())
    assert plugin.summarize([{"role": "user", "content": "hi"}]) == "ok"
    assert seen[0][0] == {"role": "system", "content": SUMMARIZE_INSTRUCTIONS}
    assert seen[0][1]["role"] == "user"


def test_unknown_summarizer_type_fails() -> None:
    with pytest.raises(KeyError, match="spec.summarizer"):
        CMFactory.create(
            spec={"type": "summarising", "params": {"summarizer": "not-a-plugin"}},
        )
