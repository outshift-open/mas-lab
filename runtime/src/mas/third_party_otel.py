#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Keep third-party OpenTelemetry instrumentation off unless the user opts in.

MAS Lab emits OTel only through the ``otel`` observability plugin. Recent
a2a-sdk releases turn tracing on whenever ``opentelemetry`` is importable
(default ``OTEL_INSTRUMENTATION_A2A_SDK_ENABLED=true``), wrapping async
work in ``start_as_current_span``. Those spans attach/detach contextvars
tokens. When the work finishes on another thread or asyncio task — the A2A
client's thread-pool ``asyncio.run`` bridge does exactly that —
OpenTelemetry logs ``ValueError: Token was created in a different Context``
at ERROR, one full traceback per call (GitHub issue #127).

The flag is read once at import of ``a2a.utils.telemetry``. This module
must run before any ``a2a`` import. Importing it has the pin as a side
effect; ``pin_third_party_otel_off`` is also safe to call explicitly.

This does **not** set ``OTEL_SDK_DISABLED``. That would disable the
first-party ``otel`` plugin. Explicit ``OTEL_INSTRUMENTATION_A2A_SDK_ENABLED=true``
in the process environment is left alone (``setdefault``).
"""

from __future__ import annotations

import os

A2A_SDK_OTEL_FLAG = "OTEL_INSTRUMENTATION_A2A_SDK_ENABLED"


def pin_third_party_otel_off() -> None:
    """Default-disable a2a-sdk self-instrumentation if the user did not opt in."""
    os.environ.setdefault(A2A_SDK_OTEL_FLAG, "false")


pin_third_party_otel_off()
