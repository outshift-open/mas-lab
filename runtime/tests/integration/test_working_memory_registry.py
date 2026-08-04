#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Session-scoped working memory registry — spec.working_memory.persistent backing store."""

from types import SimpleNamespace

from mas.runtime.boundary.context.working_memory_registry import (
    WorkingMemoryConfig,
    WorkingMemoryRegistry,
    WorkingMemorySnapshot,
    clear_ctx_working_memory,
    get_working_memory_registry,
    is_persistent,
    reset_working_memory_registry,
    restore_ctx,
    snapshot_ctx,
    sync_working_memory_in,
    sync_working_memory_out,
)


class _FakeCtx:
    def __init__(self, turn_history=None, committed_messages=None):
        self.turn_history = list(turn_history or [])
        self.committed_messages = list(committed_messages or [])


def _fake_instance(*, persistent: bool = True, ctx: "_FakeCtx | None" = None) -> SimpleNamespace:
    return SimpleNamespace(
        driver=SimpleNamespace(ctx=ctx if ctx is not None else _FakeCtx()),
        working_memory=WorkingMemoryConfig(persistent=persistent),
    )


def test_get_returns_none_for_unknown_key():
    registry = WorkingMemoryRegistry()
    assert registry.get("session-a", "agent-a") is None


def test_put_then_get_round_trips_by_session_and_agent():
    registry = WorkingMemoryRegistry()
    snapshot = WorkingMemorySnapshot(
        turn_history=[("hi", "hello")],
        committed_messages=[{"role": "user", "content": "hi"}],
    )
    registry.put("session-a", "agent-a", snapshot)

    assert registry.get("session-a", "agent-a") == snapshot
    # Different session or different agent must not see it.
    assert registry.get("session-b", "agent-a") is None
    assert registry.get("session-a", "agent-b") is None


def test_drop_removes_only_the_targeted_key():
    registry = WorkingMemoryRegistry()
    registry.put("session-a", "agent-a", WorkingMemorySnapshot())
    registry.put("session-a", "agent-b", WorkingMemorySnapshot())

    registry.drop("session-a", "agent-a")

    assert registry.get("session-a", "agent-a") is None
    assert registry.get("session-a", "agent-b") is not None


def test_clear_session_drops_every_agent_in_that_session_only():
    registry = WorkingMemoryRegistry()
    registry.put("session-a", "agent-a", WorkingMemorySnapshot())
    registry.put("session-a", "agent-b", WorkingMemorySnapshot())
    registry.put("session-b", "agent-a", WorkingMemorySnapshot())

    registry.clear_session("session-a")

    assert registry.get("session-a", "agent-a") is None
    assert registry.get("session-a", "agent-b") is None
    assert registry.get("session-b", "agent-a") is not None


def test_put_ignores_empty_session_or_agent_id():
    registry = WorkingMemoryRegistry()
    registry.put("", "agent-a", WorkingMemorySnapshot(turn_history=[("q", "a")]))
    registry.put("session-a", "", WorkingMemorySnapshot(turn_history=[("q", "a")]))
    assert registry.get("", "agent-a") is None
    assert registry.get("session-a", "") is None


def test_snapshot_ctx_captures_committed_messages_and_turn_history():
    ctx = _FakeCtx(
        turn_history=[("foo?", "here is foo")],
        committed_messages=[
            {"role": "user", "content": "foo?"},
            {"role": "assistant", "content": "here is foo"},
        ],
    )
    snapshot = snapshot_ctx(ctx)
    assert snapshot.turn_history == [("foo?", "here is foo")]
    assert snapshot.committed_messages == [
        {"role": "user", "content": "foo?"},
        {"role": "assistant", "content": "here is foo"},
    ]
    # Snapshot must be a copy, not a live view — mutating ctx afterwards
    # must not retroactively change what was captured.
    ctx.committed_messages.append({"role": "user", "content": "mutated"})
    assert snapshot.committed_messages[-1]["content"] == "here is foo"


def test_restore_ctx_replaces_the_cross_turn_buffer():
    ctx = _FakeCtx()
    snapshot = WorkingMemorySnapshot(
        turn_history=[("foo?", "here is foo")],
        committed_messages=[{"role": "user", "content": "foo?"}],
    )
    restore_ctx(ctx, snapshot)
    assert ctx.turn_history == [("foo?", "here is foo")]
    assert ctx.committed_messages == [{"role": "user", "content": "foo?"}]


def test_clear_ctx_working_memory_empties_history_without_touching_other_fields():
    ctx = _FakeCtx(turn_history=[("foo?", "here is foo")], committed_messages=[{"role": "user", "content": "foo?"}])
    ctx.injected_context = ["system prompt line"]
    clear_ctx_working_memory(ctx)
    assert ctx.turn_history == []
    assert ctx.committed_messages == []
    assert ctx.injected_context == ["system prompt line"]


def test_process_wide_registry_is_a_singleton():
    reset_working_memory_registry()
    get_working_memory_registry().put("s", "a", WorkingMemorySnapshot(turn_history=[("q", "a")]))
    assert get_working_memory_registry().get("s", "a") is not None
    reset_working_memory_registry()
    assert get_working_memory_registry().get("s", "a") is None


def test_is_persistent_defaults_true_when_working_memory_unset():
    assert is_persistent(SimpleNamespace()) is True


def test_is_persistent_reads_working_memory_config():
    assert is_persistent(_fake_instance(persistent=True)) is True
    assert is_persistent(_fake_instance(persistent=False)) is False


def test_sync_working_memory_in_restores_a_prior_snapshot():
    reset_working_memory_registry()
    get_working_memory_registry().put(
        "s", "a", WorkingMemorySnapshot(committed_messages=[{"role": "user", "content": "hi"}])
    )
    instance = _fake_instance()
    sync_working_memory_in(instance, memory_key="s", agent_id="a")
    assert instance.driver.ctx.committed_messages == [{"role": "user", "content": "hi"}]


def test_sync_working_memory_in_clears_when_no_snapshot_exists():
    reset_working_memory_registry()
    ctx = _FakeCtx(committed_messages=[{"role": "user", "content": "stale"}])
    instance = _fake_instance(ctx=ctx)
    sync_working_memory_in(instance, memory_key="new-bucket", agent_id="a")
    assert ctx.committed_messages == []


def test_sync_working_memory_in_always_clears_when_not_persistent():
    reset_working_memory_registry()
    get_working_memory_registry().put(
        "s", "a", WorkingMemorySnapshot(committed_messages=[{"role": "user", "content": "hi"}])
    )
    instance = _fake_instance(persistent=False)
    sync_working_memory_in(instance, memory_key="s", agent_id="a")
    assert instance.driver.ctx.committed_messages == []


def test_sync_working_memory_out_saves_the_current_ctx_state():
    reset_working_memory_registry()
    ctx = _FakeCtx(committed_messages=[{"role": "user", "content": "hi"}])
    instance = _fake_instance(ctx=ctx)
    sync_working_memory_out(instance, memory_key="s", agent_id="a")
    snapshot = get_working_memory_registry().get("s", "a")
    assert snapshot is not None
    assert snapshot.committed_messages == [{"role": "user", "content": "hi"}]


def test_sync_working_memory_out_does_not_save_when_not_persistent():
    reset_working_memory_registry()
    ctx = _FakeCtx(committed_messages=[{"role": "user", "content": "hi"}])
    instance = _fake_instance(persistent=False, ctx=ctx)
    sync_working_memory_out(instance, memory_key="s", agent_id="a")
    assert get_working_memory_registry().get("s", "a") is None
