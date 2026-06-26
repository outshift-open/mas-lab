#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Compose pipeline — mas-ctl bind models and placement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mas.ctl.compose.models import (
    ComposedApplication,
    EffectiveBindManifest,
    PlacementPlan,
    ResolvedInfra,
)

if TYPE_CHECKING:
    from mas.ctl.compose.placement_registry import MaterializedRun
    from mas.ctl.compose.pipeline import (
        compose_application,
        compose_effective_bind,
        compose_placement_from_deployment,
    )

__all__ = [
    "ComposedApplication",
    "EffectiveBindManifest",
    "MaterializedRun",
    "PlacementPlan",
    "ResolvedInfra",
    "compose_application",
    "compose_effective_bind",
    "compose_placement_from_deployment",
    "get_placement_backend",
]


def __getattr__(name: str):
    """Lazy exports — avoid import cycles with session.bootstrap."""
    if name == "MaterializedRun":
        from mas.ctl.compose.placement_registry import MaterializedRun

        return MaterializedRun
    if name == "get_placement_backend":
        from mas.ctl.compose.placement_registry import get_placement_backend

        return get_placement_backend
    if name == "compose_application":
        from mas.ctl.compose.pipeline import compose_application

        return compose_application
    if name == "compose_effective_bind":
        from mas.ctl.compose.pipeline import compose_effective_bind

        return compose_effective_bind
    if name == "compose_placement_from_deployment":
        from mas.ctl.compose.pipeline import compose_placement_from_deployment

        return compose_placement_from_deployment
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
