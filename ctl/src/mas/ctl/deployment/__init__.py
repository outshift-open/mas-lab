#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Deployment manifest loading and runtime selection (kernel / Rust / future)."""

from mas.ctl.deployment.load import (
    default_deployment,
    load_deployment,
    load_deployment_for_run,
    resolve_runtime_id,
    resolve_runtime_id_for_run,
    runtime_id_from_deployment,
)
from mas.ctl.deployment.runtime_id import is_default_runtime, normalize_runtime_id
from mas.ctl.registry.catalog import list_runtime_ids, validate_runtime_id

__all__ = [
    "default_deployment",
    "is_default_runtime",
    "list_runtime_ids",
    "load_deployment",
    "load_deployment_for_run",
    "normalize_runtime_id",
    "resolve_runtime_id",
    "resolve_runtime_id_for_run",
    "runtime_id_from_deployment",
    "validate_runtime_id",
]
