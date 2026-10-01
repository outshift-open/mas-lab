#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Minimal Letta wrapper — local to this lab.

This is a thin adapter around upstream Letta Block/Memory classes that
implements the MAS ContextContract. It is intentionally minimal and
self-contained; the full implementation lives in mas-library-memory
(released separately).
"""

from .letta_wrapper import LettaCoreMemoryWrapper

__all__ = ["LettaCoreMemoryWrapper"]
