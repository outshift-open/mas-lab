#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Ingress governance validation integration."""

from mas.runtime.boundary.ingress_validate import ingress_governance_valid, validate_ingress
from mas.runtime.schema.ingress import EngineIoReturn, UserInputReceived


def test_ingress_governance_valid_accepts_monotonic_correlation():
    event = EngineIoReturn(
        correlation_id=2,
        response_kind="MODEL_TEXT",
        next_step="STOP",
        text="ok",
    )
    assert ingress_governance_valid(event, last_correlation_id=1)


def test_ingress_governance_valid_rejects_stale_correlation():
    event = EngineIoReturn(
        correlation_id=1,
        response_kind="MODEL_TEXT",
        next_step="STOP",
        text="ok",
    )
    assert not ingress_governance_valid(event, pending_correlation_id=2)


def test_validate_ingress_passes_non_engine_events():
    assert validate_ingress(UserInputReceived(user_turn_id="u1", text="hi"))
