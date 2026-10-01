#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Observability export plugins (library-standard — not runtime, not ctl).

The ``otel`` plugin is imported lazily. Loading ``native`` (the default)
must not import OpenTelemetry — that is what makes a2a-sdk decide that
instrumentation is available and start emitting spans on its own.
"""

from __future__ import annotations

from typing import Any

from mas.library.standard.plugins.observability.native_plugin import NativeObservabilityPlugin

__all__ = [
    "NativeObservabilityPlugin",
    "OtelObservabilityPlugin",
]


def __getattr__(name: str) -> Any:
    if name == "OtelObservabilityPlugin":
        from mas.library.standard.plugins.observability.otel_plugin import (
            OtelObservabilityPlugin,
        )

        return OtelObservabilityPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
