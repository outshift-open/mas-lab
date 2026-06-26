#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Wire observability pipeline onto a runtime instance."""

from __future__ import annotations

from pathlib import Path

from mas.ctl.adapters.obs.bridge import attach_observability
from mas.ctl.adapters.obs.pipeline import ObservabilityConfig, ObservabilityPipeline, build_pipeline
from mas.ctl.adapters.obs.session import SessionObservabilityRecorder
from mas.runtime.driver.instance import RuntimeInstance


def setup_observability(
    instance: RuntimeInstance,
    config: ObservabilityConfig,
    *,
    base_dir: Path,
) -> SessionObservabilityRecorder | None:
    pipeline = build_pipeline(config, base_dir=base_dir)
    if pipeline is None:
        return None
    attach_observability(instance, pipeline)
    return SessionObservabilityRecorder(pipeline=pipeline)
