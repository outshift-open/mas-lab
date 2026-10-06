#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Telemetry codecs — (artifact_kind, store_type) serialize/deserialize pairs.

A **codec** is the library's independent, registered converter between a span
artifact and a store, invoked implicitly at step/infra boundaries. Counterpart
of the OTel span *artifact* (:class:`~mas.library.telemetry.artifact.OtelSpanSet`).

Registered codecs (artifact kind ``otel_traces``):

* ``("otel_traces", "otlp")``       — :class:`OtlpSpansCodec`. ``encode`` pushes
  spans to an OTLP collector. (Collectors are write-only; ``decode`` reads back
  from ClickHouse via the codec below.)
* ``("otel_traces", "clickhouse")`` — :class:`ClickHouseSpansCodec`. ``decode``
  fetches a session's spans from a ClickHouse ``otel_traces`` table into an
  ``OtelSpanSet``.

Discovery for other plugins in this repo is via each library's ``library.yaml``
manifest, resolved lazily by ``mas.lab.benchmark.codecs.get_codec`` -- but these
two are NOT YET declared there: ``mas-lab``'s own ``library-lab`` registers
generic codecs under the same ``(otel_traces, otlp)``/``(otel_traces,
clickhouse)`` keys, and adding these here today would just silently flip which
implementation wins rather than fix that collision. Until that's resolved,
these classes are only reachable by importing them directly, not via
``get_codec``. Requires the bench framework (``[bench]`` extra).
"""

from __future__ import annotations

from typing import Any

from mas.lab.benchmark.codecs.base import Codec

from mas.library.telemetry.artifact import OtelSpanSet
from mas.library.telemetry.collector.otlp import push_spans_to_collector

__all__ = ["OtlpSpansCodec", "ClickHouseSpansCodec"]


class OtlpSpansCodec(Codec):
    """Serialize an OTel span set to an ``otlp`` collector (write-only)."""

    artifact_kind: str = "otel_traces"
    store_type: str = "otlp"

    def encode(self, artifact: Any, **opts: Any) -> None:
        spans = artifact.spans if isinstance(artifact, OtelSpanSet) else artifact
        endpoint = (
            getattr(self.store, "uri", None)
            or getattr(self.store, "endpoint", None)
            or opts.get("endpoint")
        )
        if not endpoint:
            raise ValueError(
                "OtlpSpansCodec.encode: no OTLP endpoint on the store spec"
            )
        result = push_spans_to_collector(
            spans,
            endpoint,
            service_name=str(opts.get("service_name", "mas-runtime")),
            app_name=str(opts.get("app_name", "")),
            dry_run=bool(opts.get("dry_run", False)),
        )
        if result.get("status") not in {"ok", "dry-run"}:
            raise RuntimeError(
                f"OtlpSpansCodec.encode: OTLP push failed — {result.get('detail')}"
            )

    def decode(self, **opts: Any) -> Any:
        raise NotImplementedError(
            "OtlpSpansCodec: collectors are write-only; read spans back with the "
            "('otel_traces', 'clickhouse') codec."
        )


class ClickHouseSpansCodec(Codec):
    """Deserialize a session's OTel spans from a ``clickhouse`` ``otel_traces`` table."""

    artifact_kind: str = "otel_traces"
    store_type: str = "clickhouse"

    def decode(self, **opts: Any) -> OtelSpanSet:
        session_id = opts.get("session_id") or opts.get("run_id")
        if not session_id:
            raise ValueError(
                "ClickHouseSpansCodec.decode: provide session_id or run_id in opts."
            )
        return OtelSpanSet.fetch_from_clickhouse(
            session_id,
            query_by=str(opts.get("query_by", "session")),
            host=getattr(self.store, "host", None),
            port=getattr(self.store, "port", None),
            user=getattr(self.store, "user", None),
            database=getattr(self.store, "database", None),
            password_env=getattr(self.store, "password_env", None)
            or "CLICKHOUSE_PASSWORD",
            table=str(opts.get("table", "otel_traces")),
        )

    def encode(self, artifact: Any, **opts: Any) -> None:
        raise NotImplementedError(
            "ClickHouseSpansCodec: write spans via the ('otel_traces', 'otlp') codec "
            "(push to a collector that ingests into ClickHouse)."
        )
