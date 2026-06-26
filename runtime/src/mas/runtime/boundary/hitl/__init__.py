#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Mock HITL operators for tests and simulated runtime."""

from mas.runtime.boundary.hitl.responders import (
    AutoApproveResponder,
    AutoDenyResponder,
    AutoTerminateResponder,
    HitlResponder,
    MultiOperatorHitlResponder,
    OperatorPersona,
    ScriptedHitlResponder,
)

__all__ = [
    "AutoApproveResponder",
    "AutoDenyResponder",
    "AutoTerminateResponder",
    "HitlResponder",
    "MultiOperatorHitlResponder",
    "OperatorPersona",
    "ScriptedHitlResponder",
]
