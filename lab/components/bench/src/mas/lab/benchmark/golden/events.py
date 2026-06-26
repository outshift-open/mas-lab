#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Normalize and compare events.jsonl for golden-run regression tests."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator

# Fields that vary run-to-run but carry no semantic signal for parity tests.
_STRIP_KEYS = frozenset({
    "timestamp",
    "run_id",
    "turn_id",
    "call_id",
    "session_id",
    "trace_id",
    "span_id",
    "created_at",
    "referenced_at",
    "executed_at",
})

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)
_RUN_ID_RE = re.compile(r"^run-[0-9a-f]{8,}$", re.I)


def _scrub_value(key: str, value: Any) -> Any:
    if key in _STRIP_KEYS:
        return "<stripped>"
    if isinstance(value, str):
        if _UUID_RE.match(value) or _RUN_ID_RE.match(value):
            return "<id>"
    if isinstance(value, dict):
        return _normalize_event(value)
    if isinstance(value, list):
        return [_scrub_value("", v) if not isinstance(v, (dict, list)) else v for v in value]
    return value


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted(event.keys()):
        out[key] = _scrub_value(key, event[key])
    return out


def normalize_events_lines(lines: Iterator[str]) -> list[dict[str, Any]]:
    """Parse and normalize events, preserving order."""
    normalized: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            normalized.append(_normalize_event(event))
    return normalized


def normalize_events_file(path: Path) -> list[dict[str, Any]]:
    return normalize_events_lines(path.read_text(encoding="utf-8").splitlines())


def events_fingerprint(events: list[dict[str, Any]]) -> str:
    payload = json.dumps(events, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_events_files(actual: Path, expected: Path) -> tuple[bool, str]:
    """Return (match, diff_summary)."""
    act = normalize_events_file(actual)
    exp = normalize_events_file(expected)
    if events_fingerprint(act) == events_fingerprint(exp):
        return True, ""
    if len(act) != len(exp):
        return False, f"event count {len(act)} != {len(exp)}"
    for i, (a, e) in enumerate(zip(act, exp)):
        if a != e:
            return False, f"first diff at index {i}: {json.dumps(a)[:200]} != {json.dumps(e)[:200]}"
    return False, "fingerprint mismatch"


def write_normalized_events(events: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n")
