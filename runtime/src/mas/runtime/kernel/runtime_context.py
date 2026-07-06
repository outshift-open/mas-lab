#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Instance-scoped runtime bindings for kernel hot-path hooks.

Coordination and governance observability were previously module globals rebound on
every :meth:`KernelDriver.feed`, which is unsafe when multiple drivers run
concurrently (threads or overlapping async tasks). Bindings are stored in
:class:`contextvars.ContextVar` holders and activated for the duration of each
feed via :func:`runtime_binding`.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from mas.runtime.boundary.obs.operator import ObservabilityOperator
    from mas.runtime.kernel.coord_hook import CoordHook

_coord: ContextVar[CoordHook | None] = ContextVar("_coord", default=None)
_recorder: ContextVar[ObservabilityOperator | None] = ContextVar("_recorder", default=None)


def get_coordination() -> CoordHook | None:
    return _coord.get()


def set_coordination(coord: CoordHook | None) -> Token:
    return _coord.set(coord)


def reset_coordination(token: Token) -> None:
    _coord.reset(token)


def get_governance_observability() -> ObservabilityOperator | None:
    return _recorder.get()


def set_governance_observability(recorder: ObservabilityOperator | None) -> Token:
    return _recorder.set(recorder)


def reset_governance_observability(token: Token) -> None:
    _recorder.reset(token)


@contextmanager
def runtime_binding(
    coord: CoordHook | None,
    observability: ObservabilityOperator | None,
) -> Iterator[None]:
    """Activate coordination/obs bindings for one driver feed (thread/task local)."""
    coord_token = set_coordination(coord)
    obs_token = set_governance_observability(observability)
    try:
        yield
    finally:
        reset_coordination(coord_token)
        reset_governance_observability(obs_token)
