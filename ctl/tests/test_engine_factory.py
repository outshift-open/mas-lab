#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Engine selection — explicit mock/live only; no silent SimulatedEngine fallback."""

from __future__ import annotations

import pytest

from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.session.engine_factory import build_engine
from mas.runtime.driver.mocks import AutoCtxAssembler


def test_build_engine_errors_without_infra_or_mock():
    ctx = AutoCtxAssembler()
    manifest = {"spec": {"models": [{"model": "gpt-4o"}]}}

    with pytest.raises(RuntimeError, match="No LLM configured"):
        build_engine(ctx, manifest, ResolvedInfra(refs=[], llm_proxy={}))


def test_build_engine_mock_mode_from_execution_flag():
    ctx = AutoCtxAssembler()
    manifest = {"spec": {"execution": {"mocking": {"enabled": True}}}}

    sel = build_engine(ctx, manifest, ResolvedInfra(refs=[], llm_proxy={}))
    assert sel.mode == "mock"
