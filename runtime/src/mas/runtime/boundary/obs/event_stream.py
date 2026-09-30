#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Process-wide live telemetry bus for pipeline steps and demo UI sinks."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Any, Callable

Subscriber = Callable[[dict[str, Any]], None]

_logger = logging.getLogger(__name__)
_current: ContextVar["EventStream | None"] = ContextVar("mas_event_stream", default=None)


class EventStream:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        if fn not in self._subscribers:
            self._subscribers.append(fn)

        def _unsubscribe() -> None:
            self.unsubscribe(fn)

        return _unsubscribe

    def unsubscribe(self, fn: Subscriber) -> None:
        self._subscribers = [s for s in self._subscribers if s is not fn]

    def publish(self, event: dict[str, Any]) -> None:
        for fn in list(self._subscribers):
            try:
                fn(event)
            except Exception:
                _logger.warning("event subscriber failed: %s", fn, exc_info=True)


def get_event_stream() -> EventStream | None:
    return _current.get()


def set_event_stream(stream: EventStream | None) -> Token:
    return _current.set(stream)


def reset_event_stream(token: Token) -> None:
    _current.reset(token)


def publish_event(event: dict[str, Any]) -> None:
    stream = get_event_stream()
    if stream is not None:
        stream.publish(event)
