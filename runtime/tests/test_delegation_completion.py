#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation completion helpers."""

from mas.runtime.boundary.delegation.completion import (
    continuation_prompt_for_verification,
    verification_status,
)


def test_verification_status_parses_approved():
    assert verification_status("Checks ok.\nVERIFICATION: APPROVED") == "APPROVED"


def test_verification_status_missing():
    assert verification_status("partial output only") is None


def test_continuation_prompt_for_verifier():
    prompt = continuation_prompt_for_verification("partial")
    assert "VERIFICATION:" in prompt
    assert "partial" in prompt
