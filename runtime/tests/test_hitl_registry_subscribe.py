#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""HitlResolverRegistry.subscribe(): synchronous, additive notification on
register() -- replaces polling get_pending_for_session() in a retry loop to
bridge the gap between "tool call started" and "request is in the registry"."""

from __future__ import annotations

from mas.runtime.boundary.hitl.registry import HitlResolverRegistry
from mas.runtime.schema.hitl import HitlQuestionType


def _register(registry: HitlResolverRegistry, *, session_id: str = "s1", correlation_id: int = 1) -> None:
    registry.register(
        session_id=session_id,
        agent_id="finance-agent",
        correlation_id=correlation_id,
        question="Approve 20% discount?",
        question_type=HitlQuestionType.CONFIRM,
        choices=["approve", "reject"],
        context_data={},
    )


def test_subscriber_notified_synchronously_on_register():
    registry = HitlResolverRegistry()
    received = []
    registry.subscribe(received.append)

    _register(registry)

    assert len(received) == 1
    assert received[0].question == "Approve 20% discount?"


def test_multiple_subscribers_all_notified():
    registry = HitlResolverRegistry()
    a, b = [], []
    registry.subscribe(a.append)
    registry.subscribe(b.append)

    _register(registry)

    assert len(a) == 1 and len(b) == 1


def test_unsubscribe_stops_notifications():
    registry = HitlResolverRegistry()
    received = []
    registry.subscribe(received.append)
    registry.unsubscribe(received.append)

    _register(registry)

    assert received == []


def test_subscribing_same_callback_twice_is_a_noop():
    registry = HitlResolverRegistry()
    received = []
    registry.subscribe(received.append)
    registry.subscribe(received.append)

    _register(registry)

    assert len(received) == 1


def test_subscriber_exception_does_not_break_registration_or_other_subscribers():
    registry = HitlResolverRegistry()
    received = []

    def boom(_request):
        raise RuntimeError("boom")

    registry.subscribe(boom)
    registry.subscribe(received.append)

    _register(registry)

    assert len(received) == 1
    assert registry.has_pending("s1", "finance-agent")


def test_user_update_subscriber_notified_on_register_user_update():
    registry = HitlResolverRegistry()
    received = []
    registry.subscribe_user_update(received.append)

    registry.register_user_update(
        session_id="s1", agent_id="moderator", correlation_id=1, message="Checking with Finance..."
    )

    assert len(received) == 1
    assert received[0].message == "Checking with Finance..."
