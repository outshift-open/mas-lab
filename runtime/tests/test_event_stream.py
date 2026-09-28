#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mas.runtime.boundary.obs.event_stream import (
    EventStream,
    get_event_stream,
    publish_event,
    reset_event_stream,
    set_event_stream,
)
from mas.runtime.boundary.obs.operator import ObservabilityOperator
from mas.runtime.boundary.obs.transition import TransitionEvent


def test_event_stream_publish_subscribe() -> None:
    stream = EventStream()
    seen: list[dict] = []
    stream.subscribe(seen.append)
    stream.publish({"kind": "x", "n": 1})
    assert seen == [{"kind": "x", "n": 1}]


def test_contextvar_publish() -> None:
    stream = EventStream()
    token = set_event_stream(stream)
    try:
        seen: list[dict] = []
        stream.subscribe(seen.append)
        publish_event({"kind": "y"})
        assert seen[0]["kind"] == "y"
        assert get_event_stream() is stream
    finally:
        reset_event_stream(token)
    assert get_event_stream() is None


def test_event_stream_keeps_running_when_a_subscriber_fails() -> None:
    stream = EventStream()
    seen: list[dict] = []

    def broken(_: dict) -> None:
        raise RuntimeError("boom")

    stream.subscribe(broken)
    stream.subscribe(seen.append)
    stream.publish({"kind": "z"})

    assert seen == [{"kind": "z"}]


def test_event_stream_subscription_can_be_cleared() -> None:
    stream = EventStream()
    seen: list[dict] = []

    unsubscribe = stream.subscribe(seen.append)
    unsubscribe()
    stream.publish({"kind": "q"})

    assert seen == []


def test_operator_dispatch_publishes_even_without_plugins() -> None:
    stream = EventStream()
    token = set_event_stream(stream)
    seen: list[dict] = []
    stream.subscribe(seen.append)
    try:
        op = ObservabilityOperator()
        op._dispatch_transition(
            TransitionEvent(contract_id="tool", mealy_symbol="TOOL_CALL", phase="end", agent_id="moderator")
        )
        assert seen
        assert seen[0]["source"] == "transition"
        assert seen[0]["contract_id"] == "tool"
        assert seen[0]["agent_id"] == "moderator"
    finally:
        reset_event_stream(token)
