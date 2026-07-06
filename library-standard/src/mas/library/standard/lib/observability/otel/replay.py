#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Offline replay: convert a native events.jsonl file to OTel SDK spans.

Extracted from ``MasOtelConverter`` so the converter class stays focused on
live event → span mapping.  Use :func:`replay_events_file` directly; the
``MasOtelConverter.replay_file`` classmethod delegates here for backward compat.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mas.library.standard.lib.observability.export_layers import ExportLayers, parse_export_layers

logger = logging.getLogger(__name__)


def replay_events_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    service_name: str = "agent-runtime",
    app_name: str = "",
    flush_timeout_ms: int = 5000,
    export_layers: ExportLayers | dict[str, Any] | None = None,
) -> int:
    """Replay an events.jsonl file and write OTel spans to *output_path*.

    This is the canonical converter from MAS native events to OTel SDK spans.
    All event kinds supported by :class:`~mas.library.standard.lib.observability.otel.converter.MasOtelConverter`
    are converted; the output is safe to push with
    :func:`mas.lab.telemetry.otlp_push.push_file` or any OTel-aware tool.

    Parameters
    ----------
    input_path:
        Path to the ``events.jsonl`` file produced by the native plugin.
    output_path:
        Destination ``otel_sdk_spans.jsonl`` file (one SDK span per line).
    service_name:
        OTel ``service.name`` resource attribute.
    app_name:
        When non-empty, sets ``application_id`` on every span.
        Defaults to ``service_name`` when not provided.
    flush_timeout_ms:
        Milliseconds to wait for the span processor to flush on shutdown.
    export_layers:
        Layer filter; defaults to structure + execution + semantic.

    Returns
    -------
    int
        Number of events processed.
    """
    from mas.library.standard.lib.observability.otel.converter import (
        OTEL_AVAILABLE,
        JSONLineFileSpanExporter,
        MasOtelConverter,
    )

    if not OTEL_AVAILABLE:
        raise RuntimeError("opentelemetry-sdk is not installed")

    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"events.jsonl not found: {input_path}")

    effective_app_name = app_name or service_name
    exporter = JSONLineFileSpanExporter(output_path)
    resource = Resource.create({
        "service.name": service_name,
        "mas.instrumentation.version": "1.0.0",
        "mas.plugin": "MasOtelConverter.replay",
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("mas-otel-converter")

    layers = (
        export_layers
        if isinstance(export_layers, ExportLayers)
        else parse_export_layers(export_layers if isinstance(export_layers, dict) else None)
    )
    converter = MasOtelConverter(tracer, app_name=effective_app_name, export_layers=layers)
    # Deterministic session_uuid per (file, service) for stable span IDs across replays.
    converter._session_uuid = hashlib.sha256(
        f"{input_path.resolve()}:{service_name}".encode()
    ).hexdigest()

    first_event: dict[str, Any] | None = None
    count = 0
    with open(input_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if first_event is None:
                    first_event = event
                converter.process_event(event)
                count += 1
            except json.JSONDecodeError:
                logger.warning("replay_events_file: skipping invalid JSON line")

    converter.flush_open_spans()
    provider.force_flush(timeout_millis=flush_timeout_ms)
    provider.shutdown()
    _write_replay_mapping(
        input_path=input_path,
        output_path=Path(output_path),
        app_name=effective_app_name,
        service_name=service_name,
        session_uuid=converter._session_uuid,
        run_id=converter._run_id,
        first_event=first_event or {},
    )
    return count


def _write_replay_mapping(
    *,
    input_path: Path,
    output_path: Path,
    app_name: str,
    service_name: str,
    session_uuid: str,
    run_id: str,
    first_event: dict[str, Any],
) -> None:
    """Append a converter replay mapping entry to session_mappings.jsonl."""
    run_info = _load_run_info(output_path.parent.parent / "run_info.json")
    task_meta = first_event.get("metadata") if isinstance(first_event, dict) else {}
    if not isinstance(task_meta, dict):
        task_meta = {}

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "converter-replay",
        "application_id": app_name,
        "session_name": app_name,
        "service_name": service_name,
        "session_uuid": session_uuid,
        "run_id": run_id,
        "experiment_id": task_meta.get("experiment_id") or run_info.get("experiment") or "",
        "scenario_id": task_meta.get("scenario_id") or run_info.get("scenario") or "",
        "test_id": task_meta.get("test_id") or "",
        "run_idx": task_meta.get("run_idx") or run_info.get("run_idx") or "",
        "item_id": task_meta.get("item_id") or run_info.get("item_id") or "",
        "input_events": str(input_path),
        "output_spans": str(output_path),
        "run_info": run_info,
    }

    targets = [output_path.parent / "session_mappings.jsonl"]
    run_cache_dir = output_path.parent.parent / "cache"
    if run_cache_dir.exists() or run_cache_dir.is_symlink():
        targets.append(run_cache_dir / "session_mappings.jsonl")
    env_cache = os.getenv("MAS_LLM_CACHE_DIR", "").strip()
    if env_cache:
        targets.append(Path(env_cache).expanduser() / "session_mappings.jsonl")

    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        except Exception:
            logger.debug("could not write mapping file: %s", target, exc_info=True)


def _load_run_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


__all__ = ["replay_events_file"]
