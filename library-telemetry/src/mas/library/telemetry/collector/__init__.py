#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OTel collector serialization — the analogue of ``mas.library.kg.neo4j``.

Where ``library-kg`` serializes a KG to Neo4j, this subpackage serializes an OTel
span set to an OTLP collector, and reads spans back out of ClickHouse.

Push (OTLP HTTP/JSON — stdlib only)
-----------------------------------
``push_file``                 — file (native events or SDK spans) → OTLP collector
``push_spans_to_collector``   — in-memory SDK spans → OTLP collector
``convert_file_to_otlp_jsonl``— write OTLP / SDK-span JSONL without pushing
``OtlpSpan``                  — minimal OTLP span data model

Read-back (requires the ``clickhouse`` extra)
---------------------------------------------
``dump_spans``                — fetch a session's spans from ClickHouse → JSONL
``list_apps``                 — list ServiceNames present in ``otel_traces``
"""

from mas.library.telemetry.collector.clickhouse import dump_spans, list_apps
from mas.library.telemetry.collector.otlp import (
    OtlpSpan,
    convert_file_to_otlp_jsonl,
    load_events,
    push_file,
    push_spans_to_collector,
)

__all__ = [
    "OtlpSpan",
    "load_events",
    "push_file",
    "push_spans_to_collector",
    "convert_file_to_otlp_jsonl",
    "dump_spans",
    "list_apps",
]
