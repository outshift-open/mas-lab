#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Kubernetes placement is not available in this release."""

from __future__ import annotations

from mas.ctl.compose.models import EffectiveBindManifest, PlacementPlan
from mas.ctl.placement.protocol import MaterializedRun, PlacementBackend


class K8sBackend(PlacementBackend):
    name = "kubernetes"

    def materialize(
        self, bind: EffectiveBindManifest, plan: PlacementPlan
    ) -> MaterializedRun:
        raise RuntimeError(
            "kubernetes placement is not available in this release."
        )
