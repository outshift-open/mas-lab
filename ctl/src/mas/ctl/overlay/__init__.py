#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Overlay merge utilities."""

from mas.ctl.overlay.merge import (
    OverlayTargetError,
    apply_document_extensions,
    apply_merge_patch,
    fanout_agent_overlay,
    merge_agent_overlay,
    merge_flavour_overlay,
    merge_overlay,
)
from mas.ctl.overlay.normalize import normalize_overlay

__all__ = [
    "OverlayTargetError",
    "apply_document_extensions",
    "apply_merge_patch",
    "fanout_agent_overlay",
    "merge_agent_overlay",
    "merge_flavour_overlay",
    "merge_overlay",
    "normalize_overlay",
]
