#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OTel span exporters — shared utilities for observability plugins.

Provides file-based, in-memory, and pipe-based OTel span exporters that both
ObserveSDKPlugin and MasOtelPlugin can use.  No dependency on
ioa_observe SDK — only standard OpenTelemetry SDK.

Architecture
------------
Spans are always produced **in memory** first (via OTel's TracerProvider).
Export destinations are composable via ``MultiSpanExporter``:

* **InMemorySpanExporter** — retains spans in-process for pipeline consumption.
* **JSONLineSpanExporter** — appends span JSON to a regular file.
* **PipeSpanExporter** — writes span JSON to a named pipe (FIFO) for streaming
  to a normalization step without disk I/O.
* **OTLP** — standard OTel ``OTLPSpanExporter`` (via Observe.init() or direct config).

``MultiSpanExporter`` fans out each batch to all configured sinks, so a single
TracerProvider can simultaneously write to file + push to an OTLP collector.
"""

from __future__ import annotations

import logging
import os
import stat
import threading
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional OTel SDK imports — graceful degradation.
# ---------------------------------------------------------------------------

OTEL_SDK_AVAILABLE = False
try:
    from opentelemetry import context as context_api  # type: ignore[import]
    from opentelemetry import trace as trace_api  # type: ignore[import]
    from opentelemetry.sdk.resources import Resource  # type: ignore[import]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import]
    from opentelemetry.sdk.trace.export import (  # type: ignore[import]
        SimpleSpanProcessor,
        SpanExporter,
        SpanExportResult,
    )
    from opentelemetry.trace import Link, SpanContext, StatusCode, TraceFlags  # type: ignore[import]

    OTEL_SDK_AVAILABLE = True
except ImportError:
    pass


if OTEL_SDK_AVAILABLE:

    class JSONLineSpanExporter(SpanExporter):  # type: ignore[misc]
        """Appends OTel ReadableSpan JSON objects as individual lines to a file.

        Truncates on first write after construction to prevent stale spans
        from accumulating across benchmark re-runs.
        """

        def __init__(self, path: Path | str) -> None:
            self._path = Path(path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._lock = threading.Lock()
            self._needs_truncate = True

        def export(self, spans: Any) -> "SpanExportResult":
            try:
                with self._lock:
                    mode = "w" if self._needs_truncate else "a"
                    with open(self._path, mode, encoding="utf-8") as fh:
                        for span in spans:
                            fh.write(span.to_json(indent=None) + "\n")
                    self._needs_truncate = False
                return SpanExportResult.SUCCESS
            except Exception:
                return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            pass

    class InMemorySpanExporter(SpanExporter):  # type: ignore[misc]
        """Collects OTel spans in memory for tests and pipelines.

        This is the primary mechanism for "spans in memory first" — downstream
        pipeline steps can call ``get_spans()`` or iterate ``.spans`` to access
        the collected data without any I/O.
        """

        def __init__(self) -> None:
            self.spans: list = []
            self._lock = threading.Lock()

        def export(self, spans: Any) -> "SpanExportResult":
            with self._lock:
                self.spans.extend(spans)
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            pass

        def clear(self) -> None:
            with self._lock:
                self.spans.clear()

        def get_spans(self, name_contains: str | None = None) -> list:
            with self._lock:
                if name_contains is None:
                    return list(self.spans)
                return [s for s in self.spans if name_contains in s.name]

    class PipeSpanExporter(SpanExporter):  # type: ignore[misc]
        """Writes span JSON to a named pipe (FIFO) for zero-disk streaming.

        Usage::

            # Create a named pipe (or use an existing one)
            import os
            os.mkfifo("/tmp/spans.pipe")

            exporter = PipeSpanExporter("/tmp/spans.pipe")

        A reader process (e.g. normalization step) reads from the pipe:

            cat /tmp/spans.pipe | python -m mas.lab.normalize --stdin

        If the pipe is not yet opened by a reader, writes will block.
        To avoid blocking in production, set ``non_blocking=True`` — spans
        are silently dropped if no reader is connected.
        """

        def __init__(self, path: Path | str, non_blocking: bool = False) -> None:
            self._path = Path(path)
            self._non_blocking = non_blocking
            self._fd: int | None = None
            self._lock = threading.Lock()
            self._fifo_created = False

        def _ensure_fifo(self) -> None:
            """Create FIFO on first use (lazy — no filesystem side effect in ``__init__``)."""
            if self._fifo_created:
                return
            if not self._path.exists():
                os.mkfifo(self._path)
                logger.info("[PipeSpanExporter] Created FIFO: %s", self._path)
            elif not stat.S_ISFIFO(self._path.stat().st_mode):
                raise ValueError(
                    f"Path {self._path} exists but is not a FIFO. "
                    "Remove it or specify a different path."
                )
            self._fifo_created = True

        def _open(self) -> int | None:
            """Open the FIFO for writing (lazy, on first export)."""
            if self._fd is not None:
                return self._fd
            self._ensure_fifo()
            flags = os.O_WRONLY
            if self._non_blocking:
                flags |= os.O_NONBLOCK
            try:
                self._fd = os.open(str(self._path), flags)
                return self._fd
            except OSError as e:
                if self._non_blocking:
                    return None  # no reader connected — drop silently
                raise e

        def export(self, spans: Any) -> "SpanExportResult":
            with self._lock:
                fd = self._open()
                if fd is None:
                    return SpanExportResult.SUCCESS  # non-blocking, no reader
                try:
                    data = b""
                    for span in spans:
                        data += (span.to_json(indent=None) + "\n").encode("utf-8")
                    os.write(fd, data)
                    return SpanExportResult.SUCCESS
                except (BrokenPipeError, OSError):
                    # Reader disconnected — reset fd for next attempt
                    self._close_fd()
                    return SpanExportResult.FAILURE

        def _close_fd(self) -> None:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None

        def shutdown(self) -> None:
            self._close_fd()

    class MultiSpanExporter(SpanExporter):  # type: ignore[misc]
        """Fan-out exporter: forwards each batch to multiple sinks.

        Allows a single TracerProvider to simultaneously export to file,
        pipe, memory, and/or OTLP without requiring multiple SpanProcessors.

        Usage::

            multi = MultiSpanExporter([
                InMemorySpanExporter(),
                JSONLineSpanExporter("traces/spans.jsonl"),
                PipeSpanExporter("/tmp/spans.pipe", non_blocking=True),
            ])
            provider.add_span_processor(SimpleSpanProcessor(multi))
        """

        def __init__(self, exporters: Sequence[SpanExporter]) -> None:
            self._exporters = list(exporters)

        def export(self, spans: Any) -> "SpanExportResult":
            results = []
            for exporter in self._exporters:
                try:
                    results.append(exporter.export(spans))
                except Exception as e:
                    logger.warning(
                        "[MultiSpanExporter] Export failed for %s: %s",
                        type(exporter).__name__, e,
                    )
                    results.append(SpanExportResult.FAILURE)
            # Return SUCCESS if at least one exporter succeeded
            if any(r == SpanExportResult.SUCCESS for r in results):
                return SpanExportResult.SUCCESS
            return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            for exporter in self._exporters:
                try:
                    exporter.shutdown()
                except Exception:
                    pass

        @property
        def exporters(self) -> list:
            """Access the underlying exporter list (for tests / introspection)."""
            return self._exporters

    def create_file_tracer_provider(
        service_name: str,
        file_path: Path | str,
    ) -> tuple["TracerProvider", "JSONLineSpanExporter"]:
        """Create a TracerProvider that exports spans to a JSONL file.

        Returns (provider, exporter) tuple.  Caller is responsible for
        calling trace_api.set_tracer_provider(provider).
        """
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        out = Path(file_path)
        if out.suffix == "":
            out = out / "traces.jsonl"
        exporter = JSONLineSpanExporter(out)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return provider, exporter

    def create_multi_sink_tracer_provider(
        service_name: str,
        *,
        file_path: Path | str | None = None,
        pipe_path: Path | str | None = None,
        in_memory: bool = False,
        non_blocking_pipe: bool = True,
    ) -> tuple["TracerProvider", dict[str, "SpanExporter"]]:
        """Create a TracerProvider with multiple export sinks.

        Returns (provider, exporters_dict) where exporters_dict maps
        sink name → exporter instance for introspection.

        Example::

            provider, sinks = create_multi_sink_tracer_provider(
                "trip-planner",
                file_path="traces/spans.jsonl",
                in_memory=True,
            )
            trace_api.set_tracer_provider(provider)

            # Later, access in-memory spans:
            mem = sinks["memory"]
            spans = mem.get_spans()
        """
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        exporters: list[SpanExporter] = []
        sinks: dict[str, SpanExporter] = {}

        if file_path is not None:
            out = Path(file_path)
            if out.suffix == "":
                out = out / "observe_sdk_spans.jsonl"
            exp = JSONLineSpanExporter(out)
            exporters.append(exp)
            sinks["file"] = exp

        if pipe_path is not None:
            exp = PipeSpanExporter(pipe_path, non_blocking=non_blocking_pipe)
            exporters.append(exp)
            sinks["pipe"] = exp

        if in_memory:
            exp = InMemorySpanExporter()
            exporters.append(exp)
            sinks["memory"] = exp

        if len(exporters) == 1:
            provider.add_span_processor(SimpleSpanProcessor(exporters[0]))
        elif len(exporters) > 1:
            multi = MultiSpanExporter(exporters)
            provider.add_span_processor(SimpleSpanProcessor(multi))

        return provider, sinks

else:
    # Stubs when OTel SDK not available
    JSONLineSpanExporter = None  # type: ignore[assignment,misc]
    InMemorySpanExporter = None  # type: ignore[assignment,misc]
    PipeSpanExporter = None  # type: ignore[assignment,misc]
    MultiSpanExporter = None  # type: ignore[assignment,misc]

    def create_file_tracer_provider(service_name: str, file_path: Any) -> tuple:  # type: ignore[misc]
        raise RuntimeError("OpenTelemetry SDK not installed")

    def create_multi_sink_tracer_provider(service_name: str, **kwargs: Any) -> tuple:  # type: ignore[misc]
        raise RuntimeError("OpenTelemetry SDK not installed")
