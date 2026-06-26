#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability adapters — terminating emit protocols."""

from mas.ctl.adapters.obs.bridge import FanOutObservabilitySink, attach_observability
from mas.ctl.adapters.obs.emit import EventEmitter, JsonlFileEmitter, StdoutJsonlEmitter
from mas.ctl.adapters.obs.pipeline import ObservabilityConfig, ObservabilityPipeline, build_pipeline
from mas.ctl.adapters.obs.session import SessionObservabilityRecorder

__all__ = [
    "EventEmitter",
    "FanOutObservabilitySink",
    "JsonlFileEmitter",
    "ObservabilityConfig",
    "ObservabilityPipeline",
    "SessionObservabilityRecorder",
    "StdoutJsonlEmitter",
    "attach_observability",
    "build_pipeline",
]
