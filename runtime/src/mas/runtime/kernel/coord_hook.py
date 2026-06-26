#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Optional M_coord hook on kernel hot path (scoped via :mod:`runtime_context`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from mas.runtime.kernel.runtime_context import get_coordination

if TYPE_CHECKING:
    from mas.runtime.boundary.coordination.chokepoint import ChokepointCoordinator
    from mas.runtime.kernel.state import QProduct


class CoordHook(Protocol):
    def before_egress_governance(self, q: QProduct) -> None: ...
    def after_egress_allowed(self, q: QProduct) -> None: ...
    def on_egress_hitl(self, q: QProduct) -> None: ...
    def on_egress_blocked(self, q: QProduct) -> None: ...
    def before_ingress_governance(self, q: QProduct) -> None: ...
    def after_ingress_allowed(self, q: QProduct) -> None: ...


def bind_coordination(coord: CoordHook | None) -> None:
    """Legacy bind — prefer :func:`runtime_context.runtime_binding` per feed."""
    from mas.runtime.kernel.runtime_context import set_coordination

    set_coordination(coord)


def get_coordination() -> CoordHook | None:
    from mas.runtime.kernel.runtime_context import get_coordination as _get

    return _get()


def coord_before_egress(q: QProduct) -> None:
    coord = get_coordination()
    if coord is not None:
        coord.before_egress_governance(q)


def coord_after_egress_allowed(q: QProduct) -> None:
    coord = get_coordination()
    if coord is not None:
        coord.after_egress_allowed(q)


def coord_on_egress_hitl(q: QProduct) -> None:
    coord = get_coordination()
    if coord is not None:
        coord.on_egress_hitl(q)


def coord_on_egress_blocked(q: QProduct) -> None:
    coord = get_coordination()
    if coord is not None:
        coord.on_egress_blocked(q)


def coord_before_ingress(q: QProduct) -> None:
    coord = get_coordination()
    if coord is not None:
        coord.before_ingress_governance(q)


def coord_after_ingress(q: QProduct) -> None:
    coord = get_coordination()
    if coord is not None:
        coord.after_ingress_allowed(q)
