#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Docker placement — planned; not available in this OSS release."""

from __future__ import annotations

from mas.ctl.compose.models import EffectiveBindManifest, PlacementPlan
from mas.ctl.placement.protocol import MaterializedRun, PlacementBackend


class DockerBackend(PlacementBackend):
    name = "docker"

    def materialize(
        self, bind: EffectiveBindManifest, plan: PlacementPlan
    ) -> MaterializedRun:
        try:
            from mas.library.next.placement.docker import DockerBackend as NextDocker

            return NextDocker().materialize(bind, plan)
        except ImportError as exc:
            raise RuntimeError(
                "docker placement is not available in this OSS release (planned 2026.3)."
            ) from exc
