#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability export plugins (library-standard — not runtime, not ctl)."""

from mas.library.standard.plugins.observability.native_plugin import NativeObservabilityPlugin

__all__ = ["NativeObservabilityPlugin"]
