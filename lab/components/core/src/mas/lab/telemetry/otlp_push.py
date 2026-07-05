#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Compatibility shim — prefer ``mas.internal.telemetry.otlp_push``."""
try:
    from mas.internal.telemetry.otlp_push import (
        convert_to_jsonl,
        load_events,
        push_file,
    )
except ImportError:
    from mas.lab.telemetry._otlp_push_impl import (
        convert_to_jsonl,
        load_events,
        push_file,
    )

__all__ = ["convert_to_jsonl", "load_events", "push_file"]
