#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Re-export span parity compare from mas-lab-telemetry when installed."""

try:
    from mas.internal.telemetry.compare import (  # noqa: F401
        compare_otel_span_files,
        compare_otel_span_files_multi,
        compare_otel_span_sets,
    )
except ImportError:
    from mas.library.standard.lib.observability.otel._compare import (  # noqa: F401
        compare_otel_span_files,
        compare_otel_span_files_multi,
        compare_otel_span_sets,
    )
