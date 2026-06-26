#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mas.lab.telemetry — OTLP conversion and push utilities."""
from .otlp_push import push_file, load_events

__all__ = ["push_file", "load_events"]
