#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Commit-time conversation chunk graph."""

from __future__ import annotations

from mas.library.standard.plugins.context.provider_payload import assert_provider_payload
from mas.runtime.boundary.context.assemble import assemble_llm_messages
from mas.runtime.boundary.context.chunk_compaction import maybe_compact_chunks_after_commit
from mas.runtime.boundary.context.conversation_chunks import (
    ConversationChunkStore,
    MessageChunk,
    SummaryChunk,
)
from mas.runtime.boundary.context.working_memory_compaction import WorkingMemoryCompactionRuntime
from mas.runtime.boundary.context.working_memory_registry import (
    WorkingMemorySnapshot,
    restore_ctx,
    snapshot_ctx,
)
from mas.runtime.driver.mocks import AutoCtxAssembler


def _turn(user: str, assistant: str) -> list[dict]:
    return [
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]


def _tool_turn(call_id: str = "call_1") -> list[dict]:
    return [
        {"role": "user", "content": "ask"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "function": {"name": "search", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": call_id, "content": "result"},
        {"role": "assistant", "content": "done"},
    ]


def test_append_and_project_message_chunks() -> None:
    store = ConversationChunkStore()
    store.append_turn(_turn("q1", "a1"))
    store.append_turn(_turn("q2", "a2"))
    projected = store.project_messages()
    assert len(projected) == 4
    assert projected[0]["content"] == "q1"
    assert projected[-1]["content"] == "a2"


def test_empty_append_returns_empty_id() -> None:
    store = ConversationChunkStore()
    assert store.append_turn([]) == ""
    assert store.project_messages() == []


def test_project_summary_before_recent_chunks() -> None:
    store = ConversationChunkStore()
    store.append_turn(_turn("old", "a"))
    store.summary_chunk_id = "sum_1"
    store.chunks["sum_1"] = SummaryChunk(
        chunk_id="sum_1",
        text="rolled",
        child_chunk_ids=[],
    )
    store.append_turn(_turn("new", "b"))
    projected = store.project_messages()
    assert projected[0]["role"] == "system"
    assert projected[-1]["content"] == "b"


def test_compact_retains_child_chunks_for_audit() -> None:
    store = ConversationChunkStore()
    for i in range(6):
        store.append_turn(_turn(f"q{i}", "x" * 500))

    def summarize(msgs: list) -> str:
        return "summary-text"

    assert store.maybe_compact(
        summary_threshold=100,
        keep_message_chunks=2,
        summarize_fn=summarize,
    )
    assert store.summary_chunk_id
    summary = store.chunks[store.summary_chunk_id]
    assert isinstance(summary, SummaryChunk)
    assert summary.text == "summary-text"
    assert len(summary.child_chunk_ids) == 4
    assert len(store.order) == 2
    for child_id in summary.child_chunk_ids:
        assert child_id in store.chunks
        assert isinstance(store.chunks[child_id], MessageChunk)


def test_second_compact_is_incremental_not_full_rescan() -> None:
    store = ConversationChunkStore()
    calls = 0

    def summarize(msgs: list) -> str:
        nonlocal calls
        calls += 1
        if any("[Prior summary]" in str(m.get("content", "")) for m in msgs):
            return "summary-v2"
        return "summary-v1"

    for i in range(4):
        store.append_turn(_turn(f"q{i}", "y" * 400))
    store.maybe_compact(summary_threshold=50, keep_message_chunks=1, summarize_fn=summarize)
    store.append_turn(_turn("q4", "y" * 400))
    store.append_turn(_turn("q5", "y" * 400))
    store.maybe_compact(summary_threshold=50, keep_message_chunks=1, summarize_fn=summarize)
    assert calls == 2
    assert store.chunks[store.summary_chunk_id].text == "summary-v2"


def test_maybe_compact_noop_under_threshold() -> None:
    store = ConversationChunkStore()
    store.append_turn(_turn("a", "short"))
    assert not store.maybe_compact(
        summary_threshold=10_000,
        keep_message_chunks=1,
        summarize_fn=lambda m: "nope",
    )


def test_maybe_compact_noop_when_keep_covers_all_chunks() -> None:
    store = ConversationChunkStore()
    store.append_turn(_turn("a", "x" * 500))
    store.append_turn(_turn("b", "x" * 500))
    assert not store.maybe_compact(
        summary_threshold=10,
        keep_message_chunks=5,
        summarize_fn=lambda m: "nope",
    )


def test_serialization_round_trip() -> None:
    store = ConversationChunkStore()
    cid = store.append_turn(_turn("u", "x" * 500))
    assert store.maybe_compact(
        summary_threshold=50,
        keep_message_chunks=0,
        summarize_fn=lambda m: "sum",
    )
    restored = ConversationChunkStore.from_dict(store.to_dict())
    assert restored.summary_chunk_id == store.summary_chunk_id
    assert restored.order == store.order
    assert set(restored.chunks) == set(store.chunks)
    assert restored.project_messages() == store.project_messages()
    summary = restored.chunks[restored.summary_chunk_id]
    assert isinstance(summary, SummaryChunk)
    assert cid in summary.child_chunk_ids


def test_from_dict_none_returns_empty_store() -> None:
    store = ConversationChunkStore.from_dict(None)
    assert store.order == []
    assert store.chunks == {}


def test_assembly_uses_chunk_projection_over_flat_committed() -> None:
    ctx = AutoCtxAssembler(last_user_text="follow-up")
    ctx.committed_messages = [{"role": "user", "content": "stale"}]
    ctx.conversation_chunks.append_turn(_turn("from-chunk", "answer"))
    messages = assemble_llm_messages(ctx)
    assert any(m.get("content") == "from-chunk" for m in messages)
    assert not any(m.get("content") == "stale" for m in messages)
    assert messages[-1]["content"] == "follow-up"


def test_assembly_chunk_projection_is_provider_safe() -> None:
    ctx = AutoCtxAssembler(last_user_text="next")
    ctx.conversation_chunks.append_turn(_tool_turn("call_a"))
    ctx.conversation_chunks.append_turn(_tool_turn("call_b"))
    messages = assemble_llm_messages(ctx)
    assert_provider_payload(messages)


def test_assembly_does_not_invoke_summarize_fn() -> None:
    ctx = AutoCtxAssembler(last_user_text="q")
    ctx.working_memory_compaction = WorkingMemoryCompactionRuntime(
        summary_threshold=10,
        keep_turns=0,
        summarize_fn=lambda m: (_ for _ in ()).throw(AssertionError("no assembly summarize")),
    )
    ctx.conversation_chunks.append_turn(_turn("a", "b" * 500))
    # working_memory_compaction is commit-time only; assembly uses manifest/CMFactory.
    assemble_llm_messages(ctx)
    assemble_llm_messages(ctx)


def test_turn_commit_appends_chunk_and_compacts_at_commit_only() -> None:
    ctx = AutoCtxAssembler()
    calls = 0

    def summarize(msgs: list) -> str:
        nonlocal calls
        calls += 1
        return "rolled-up"

    ctx.working_memory_compaction = WorkingMemoryCompactionRuntime(
        summary_threshold=80,
        keep_turns=1,
        summarize_fn=summarize,
    )
    for i in range(4):
        ctx.note_user_input(f"q{i}")
        ctx.note_agent_response("x" * 200)
    assert calls >= 1
    assert ctx.conversation_chunks.summary_chunk_id
    projected = ctx.conversation_chunks.project_messages()
    assert projected[0]["role"] == "system"
    assert "rolled-up" in projected[0]["content"]


def test_maybe_compact_chunks_after_commit_respects_manifest() -> None:
    store = ConversationChunkStore()
    store.append_turn(_turn("a", "x" * 800))
    assert not maybe_compact_chunks_after_commit(store, compaction=None)
    assert maybe_compact_chunks_after_commit(
        store,
        compaction=WorkingMemoryCompactionRuntime(
            summary_threshold=50,
            keep_turns=0,
            summarize_fn=lambda m: "ok",
        ),
    )


def test_tool_trajectory_preserved_in_message_chunk() -> None:
    ctx = AutoCtxAssembler()
    ctx.note_user_input("Who is POTUS?")
    ctx.record_assistant_tool_call(call_id="call_1", tool_name="search", arguments={})
    ctx.record_tool_result(call_id="call_1", content="Donald Trump")
    ctx.note_agent_response("Donald Trump is POTUS.")
    chunk_ids = [cid for cid in ctx.conversation_chunks.order]
    assert len(chunk_ids) == 1
    chunk = ctx.conversation_chunks.chunks[chunk_ids[0]]
    assert any(m.get("role") == "tool" for m in chunk.messages)
    assert_provider_payload(chunk.messages)


def test_snapshot_round_trips_chunk_store() -> None:
    ctx = AutoCtxAssembler()
    ctx.note_user_input("hello")
    ctx.note_agent_response("world")
    snap = snapshot_ctx(ctx)
    other = AutoCtxAssembler()
    restore_ctx(other, snap)
    assert other.conversation_chunks.project_messages() == ctx.conversation_chunks.project_messages()


def test_working_memory_snapshot_carries_chunks_dict() -> None:
    ctx = AutoCtxAssembler()
    ctx.note_user_input("a")
    ctx.note_agent_response("b")
    snap = snapshot_ctx(ctx)
    assert snap.conversation_chunks is not None
    assert snap.conversation_chunks["order"]


def test_restore_empty_snapshot_clears_chunks() -> None:
    ctx = AutoCtxAssembler()
    ctx.note_user_input("a")
    ctx.note_agent_response("b")
    restore_ctx(ctx, WorkingMemorySnapshot())
    assert ctx.conversation_chunks.order == []


def test_multi_session_chunk_stores_are_independent() -> None:
    ctx_a = AutoCtxAssembler(session_id="a")
    ctx_b = AutoCtxAssembler(session_id="b")
    ctx_a.note_user_input("A")
    ctx_a.note_agent_response("a")
    ctx_b.note_user_input("B")
    ctx_b.note_agent_response("b")
    assert ctx_a.conversation_chunks.order != ctx_b.conversation_chunks.order
    msgs_a = assemble_llm_messages(ctx_a, manifest={"spec": {}})
    msgs_b = assemble_llm_messages(ctx_b, manifest={"spec": {}})
    assert any("A" in str(m.get("content")) for m in msgs_a)
    assert any("B" in str(m.get("content")) for m in msgs_b)
