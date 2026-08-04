#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""SessionController._finalize_turn — folds working memory even mid-HITL-pause."""

from __future__ import annotations

from types import SimpleNamespace

from mas.ctl.session.controller import ConversationConfig, SessionController, TurnResult
from mas.runtime.driver.mocks import AutoCtxAssembler


def _controller_with_ctx(ctx: AutoCtxAssembler, **config_kwargs) -> SessionController:
    instance = SimpleNamespace(driver=SimpleNamespace(ctx=ctx))
    return SessionController(
        instance=instance,
        display=None,
        config=ConversationConfig(**config_kwargs),
    )


def test_finalize_turn_folds_working_memory_even_when_awaiting_hitl():
    """Regression: a delegated (or any) turn paused mid-flight for HITL still
    has its already-executed tool calls folded into committed history. Before
    this fix, they sat only in ctx.working_memory and were silently wiped by
    the next turn's note_user_input() -- a real data-loss gap, not something
    a resumed HITL flow could recover from."""
    ctx = AutoCtxAssembler()
    ctx.note_user_input("please book a flight")
    ctx.record_assistant_tool_call(call_id="c1", tool_name="book_flight", arguments={"dest": "CDG"})
    ctx.record_tool_result(call_id="c1", content="awaiting approval")

    controller = _controller_with_ctx(ctx)
    result = TurnResult(trace=None, responses=[], awaiting_hitl=True)
    controller._finalize_turn(result)

    assert ctx.working_memory.messages == []  # folded in, not left dangling
    roles = [m["role"] for m in ctx.committed_messages]
    assert roles == ["user", "assistant", "tool"]
    assert ctx.committed_messages[0]["content"] == "please book a flight"


def test_finalize_turn_does_not_duplicate_the_user_turn_on_hitl_resume():
    """Regression: a turn folded once at HITL-pause time and again when
    submit_hitl() resolves it (both call _finalize_turn) used to re-append
    the SAME user message and a bogus turn_history tuple the second time,
    because note_agent_response never cleared ctx.last_user_text after
    using it -- harmless before this branch (finalize only ever ran once
    per turn), a real duplication bug once a paused turn can be folded
    twice."""
    from mas.runtime.schema.egress import EmitClientResponse

    ctx = AutoCtxAssembler()
    ctx.note_user_input("please book a flight")
    ctx.record_assistant_tool_call(call_id="c1", tool_name="book_flight", arguments={})
    ctx.record_tool_result(call_id="c1", content="awaiting approval")

    controller = _controller_with_ctx(ctx)
    controller._finalize_turn(TurnResult(trace=None, responses=[], awaiting_hitl=True))

    # Continuation after HITL approval: more tool activity, then a final answer.
    ctx.record_assistant_tool_call(call_id="c2", tool_name="book_flight", arguments={})
    ctx.record_tool_result(call_id="c2", content="booked!")
    resp = EmitClientResponse(content="Your flight is booked!", finish_reason="stop")
    controller._finalize_turn(TurnResult(trace=None, responses=[resp], awaiting_hitl=False))

    user_messages = [m for m in ctx.committed_messages if m.get("content") == "please book a flight"]
    assert len(user_messages) == 1
    assert ctx.committed_messages[-1] == {"role": "assistant", "content": "Your flight is booked!"}


def test_finalize_turn_skips_checkpoint_while_awaiting_hitl():
    ctx = AutoCtxAssembler()
    ctx.note_user_input("please book a flight")
    ctx.record_assistant_tool_call(call_id="c1", tool_name="book_flight", arguments={})
    ctx.record_tool_result(call_id="c1", content="awaiting approval")

    saved: list[dict] = []
    controller = _controller_with_ctx(ctx, save_checkpoint_each_turn=True)
    controller.instance.record_checkpoint = lambda label="": {"label": label}
    controller.checkpoint_store = SimpleNamespace(save=lambda snap: saved.append(snap))

    controller._finalize_turn(TurnResult(trace=None, responses=[], awaiting_hitl=True))

    assert saved == []  # turn isn't actually done -- no checkpoint yet


def test_finalize_turn_does_not_fold_when_nothing_happened_yet():
    """No response text and no working memory recorded -- nothing to commit,
    same as before this change (avoids inserting spurious empty turns)."""
    ctx = AutoCtxAssembler()
    controller = _controller_with_ctx(ctx)
    controller._finalize_turn(TurnResult(trace=None, responses=[], awaiting_hitl=True))
    assert ctx.committed_messages == []
    assert ctx.turn_history == []


def test_finalize_turn_completed_turn_still_commits_and_checkpoints():
    """Normal (non-HITL) path is unchanged: response text folds in and a
    completed turn still checkpoints."""
    from mas.runtime.schema.egress import EmitClientResponse

    ctx = AutoCtxAssembler()
    ctx.note_user_input("hello")
    saved: list[dict] = []
    controller = _controller_with_ctx(ctx, save_checkpoint_each_turn=True)
    controller.instance.record_checkpoint = lambda label="": {"label": label}
    controller.checkpoint_store = SimpleNamespace(save=lambda snap: saved.append(snap))

    result = TurnResult(
        trace=None,
        responses=[EmitClientResponse(content="hi there", finish_reason="stop")],
        awaiting_hitl=False,
    )
    controller._finalize_turn(result)

    assert ctx.committed_messages[-1] == {"role": "assistant", "content": "hi there"}
    assert len(saved) == 1
