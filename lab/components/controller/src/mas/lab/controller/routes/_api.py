#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared imports for route modules — patch ``mas.lab.controller.deps`` in tests."""

from mas.lab.controller import deps, jobs
from mas.lab.controller.constants import LIBRARIES_DIR, MAS_LAB_ROOT
from mas.lab.controller.pipeline_validation import validate_pipeline_yaml

__all__ = [
    "LIBRARIES_DIR",
    "MAS_LAB_ROOT",
    "deps",
    "jobs",
    "validate_pipeline_yaml",
]
