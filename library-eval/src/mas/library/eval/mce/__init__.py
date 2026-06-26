#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.library.eval.mce — MCE integration (session metrics via telemetry-hub)."""
from mas.library.eval.mce.registry_api import (
    METRIC_REGISTRY,
    build_session_from_trace,
    compute_session_metrics,
)
from mas.library.eval.mce.trace_provider import MASTraceProvider
from mas.library.eval.mce.runner import (
    ALL_SESSION_METRICS,
    METRIC_MAP,
    METRICS_SCHEMA_VERSION,
    build_metrics_document,
    compute_session_metrics as compute_trace_metrics,
    install_openai_llm_service,
)

__all__ = [
    "MASTraceProvider",
    "ALL_SESSION_METRICS",
    "METRIC_MAP",
    "METRIC_REGISTRY",
    "METRICS_SCHEMA_VERSION",
    "build_metrics_document",
    "build_session_from_trace",
    "compute_session_metrics",
    "compute_trace_metrics",
    "install_openai_llm_service",
]
