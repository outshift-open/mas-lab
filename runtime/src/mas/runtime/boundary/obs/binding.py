#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""ObservabilityBinding — frozen parsed spec struct flowing from manifest → runtime."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ObservabilityBinding:
    """Parsed ``spec.observability`` — passed from ctl into RuntimeInstance.

    All fields have safe defaults so callers can construct a minimal binding
    with just the fields they care about.
    """

    # Ordered plugin names, e.g. ["native", "otel"]
    plugins: list[str] = field(default_factory=list)
    # Per-plugin keyword config dicts, keyed by plugin name
    plugin_configs: dict[str, dict] = field(default_factory=dict)
    # Events file path (relative or absolute string; runtime resolves against base_dir)
    events_file: str | None = None
    # Name of the env-var that holds the OTLP endpoint URL
    otlp_endpoint_env: str | None = None
    # Whether to include message content in traces
    trace_content: bool = True
    # Emit events to stdout as well as file
    stdout: bool = False


__all__ = ["ObservabilityBinding"]
