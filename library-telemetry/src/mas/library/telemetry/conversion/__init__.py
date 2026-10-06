#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Native events → OTel spans conversion.

The inverse of ``library-kg``'s OTel→KG normalisation.  This subpackage takes
MAS native ``events.jsonl`` records and produces OTel spans.

Public API
----------
``MasOtelConverter``          — stateful live/replay converter (needs the SDK)
``replay_events_file``        — batch: events.jsonl → otel_sdk_spans.jsonl
``JSONLineFileSpanExporter``  — OTel SpanExporter writing one JSON line per span
``ExportLayers``              — layer toggles (structure/execution/semantic/…)
``register``                  — decorator to add a handler for a new event kind
``build_handler_table``       — assemble the full kind → handler dispatch table
``registered_kinds``          — list every event kind with a handler

Extending
---------
See :mod:`mas.library.telemetry.conversion.mappings` — add a handler in the
matching category module and decorate it with ``@register(<kind>)``.  Nothing in
the converter needs to change.
"""

from mas.library.telemetry.conversion.exporter import (
    OTEL_AVAILABLE,
    JSONLineFileSpanExporter,
)
from mas.library.telemetry.conversion.layers import (
    ExportLayers,
    parse_export_layers,
    should_export_event,
)
from mas.library.telemetry.conversion.mappings.base import (
    build_handler_table,
    register,
    registered_kinds,
)
from mas.library.telemetry.conversion.replay import replay_events_file
from mas.library.telemetry.conversion.session import create_otel_export, OtelExport

__all__ = [
    "MasOtelConverter",
    "replay_events_file",
    "create_otel_export",
    "OtelExport",
    "JSONLineFileSpanExporter",
    "OTEL_AVAILABLE",
    "ExportLayers",
    "parse_export_layers",
    "should_export_event",
    "register",
    "build_handler_table",
    "registered_kinds",
]


def __getattr__(name: str):  # pragma: no cover - lazy import guard
    # Import MasOtelConverter lazily so that merely importing the subpackage does
    # not require the OpenTelemetry SDK (the class raises if it is missing).
    if name == "MasOtelConverter":
        from mas.library.telemetry.conversion.converter import MasOtelConverter

        return MasOtelConverter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
