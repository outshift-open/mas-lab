#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Docker placement is not available in this release."""

from __future__ import annotations

from mas.ctl.compose.models import EffectiveBindManifest, PlacementPlan
from mas.ctl.placement.protocol import MaterializedRun, PlacementBackend


class DockerBackend(PlacementBackend):
    name = "docker"

    def materialize(
        self, bind: EffectiveBindManifest, plan: PlacementPlan
    ) -> MaterializedRun:
        raise RuntimeError(
            "docker placement is not available in this release."
        )
