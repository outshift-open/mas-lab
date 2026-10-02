#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Layer-2 harness compositions — plugins of plugins whose leaves are kernel ops."""

from mas.runtime.harness.catalog import (
    BOUNDARY_SLOTS,
    KERNEL_OPS,
    LIBRARY_TYPES,
    CyclicHarnessError,
    HarnessCatalog,
    HarnessComposition,
    IllegalHarnessLeafError,
    UnknownBoundarySlotError,
    classify_plugin_type,
    default_catalog,
)

__all__ = [
    "BOUNDARY_SLOTS",
    "KERNEL_OPS",
    "LIBRARY_TYPES",
    "CyclicHarnessError",
    "HarnessCatalog",
    "HarnessComposition",
    "IllegalHarnessLeafError",
    "UnknownBoundarySlotError",
    "classify_plugin_type",
    "default_catalog",
]
