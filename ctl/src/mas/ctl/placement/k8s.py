#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Kubernetes placement — planned; not available in this OSS release."""

from __future__ import annotations

from mas.ctl.compose.models import EffectiveBindManifest, PlacementPlan
from mas.ctl.placement.protocol import MaterializedRun, PlacementBackend


class K8sBackend(PlacementBackend):
    name = "kubernetes"

    def materialize(
        self, bind: EffectiveBindManifest, plan: PlacementPlan
    ) -> MaterializedRun:
        try:
            from mas.library.next.placement.k8s import K8sBackend as NextK8s

            return NextK8s().materialize(bind, plan)
        except ImportError as exc:
            raise RuntimeError(
                "kubernetes placement is not available in this OSS release (planned 2026.3)."
            ) from exc
