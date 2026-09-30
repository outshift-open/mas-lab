#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared manifest schema paths for MAS Lab components."""

from mas.lab.schemas.paths import bench_schema_dir, editor_schema_dir, runtime_schema_dir
from mas.lab.schemas.validate import (
    lab_schema_registry,
    load_lab_schema,
    schema_registry_from_dir,
    validate_against_lab_schema,
)

__all__ = [
    "bench_schema_dir",
    "editor_schema_dir",
    "runtime_schema_dir",
    "lab_schema_registry",
    "load_lab_schema",
    "schema_registry_from_dir",
    "validate_against_lab_schema",
]
