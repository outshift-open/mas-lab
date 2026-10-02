#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""retry_on_error ingress classifier + with-hardened composition."""

from __future__ import annotations

from mas.library.standard.plugins.governance.retry_on_error import RetryOnErrorPlugin
from mas.runtime.boundary.gov.error_recovery import ErrorRecoveryAction, IngressErrorContext
from mas.runtime.kernel.coupling import GovDecision
from mas.runtime.schema.governance import GovIngressProfile


def test_retry_on_error_maps_each_class() -> None:
    plugin = RetryOnErrorPlugin(
        error_policy={
            "transient": "retry",
            "unavailable": "retry",
            "application": "allow",
            "fatal": "block",
        }
    )
    ctx = IngressErrorContext(
        response_kind="ERROR",
        error_text="x",
        retry_count=0,
        max_retries=2,
        profile=GovIngressProfile.PERMISSIVE,
        failure_class="transient",
    )
    assert plugin.decide(ctx).action == ErrorRecoveryAction.RETRY
    ctx_app = IngressErrorContext(
        response_kind="TOOL_RESULT",
        error_text="bad args",
        retry_count=0,
        max_retries=2,
        profile=GovIngressProfile.PERMISSIVE,
        failure_class="application",
        failure_code="TOOL_ERROR",
    )
    assert plugin.decide(ctx_app).action == ErrorRecoveryAction.ALLOW
    ctx_fatal = IngressErrorContext(
        response_kind="ERROR",
        error_text="tls",
        retry_count=0,
        max_retries=2,
        profile=GovIngressProfile.PERMISSIVE,
        failure_class="fatal",
    )
    assert plugin.decide(ctx_fatal).action == ErrorRecoveryAction.EXIT


def test_retry_on_error_egress_always_passes() -> None:
    from mas.runtime.boundary.gov.policy import EgressIntentView
    from mas.runtime.kernel.config import KernelConfig

    plugin = RetryOnErrorPlugin()
    decision, name, _reason = plugin.evaluate_egress(
        EgressIntentView(op="TOOL_CALL", destructive=False, correlation_id=1, tool_name="x"),
        config=KernelConfig(),
    )
    assert decision == GovDecision.ALLOW
    assert name == "retry_on_error"
