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
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
_RUN_ID_RE = re.compile(r"run-[0-9a-f]{8,}", re.I)


def _scrub_value(key: str, value: Any) -> Any:
    if key in _STRIP_KEYS:
        return "<stripped>"
    if isinstance(value, str):
        # Substring substitution, not exact match: a delegated agent's own
        # exec_id/parent_call_id now embeds a real per-invocation uuid inside
        # a composite string (e.g. "schedule_agent-<uuid>-exec" — see
        # mas_session.py's make_workflow_send, which reuses caller_call_id as
        # turn_id so repeated delegation to one agent is disambiguated), not
        # a bare uuid on its own. An anchored full-string match would miss
        # this and flag two semantically-identical runs as differing purely
        # because uuid4() is random.
        scrubbed = _RUN_ID_RE.sub("<id>", _UUID_RE.sub("<id>", value))
        if scrubbed != value:
            return scrubbed
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
    """Parse and normalize events, grouped by ``agent_id`` (stable sort).

    Concurrent agents each get their own async plugin-dispatch worker thread
    (see ``ObsPluginSet.subscribe_to``), so the *interleaving* between two
    different agents' event streams in the raw file is a benign race — which
    agent's writer thread flushes first varies run to run. Each agent's own
    stream is still internally ordered (single producer thread per agent), so
    grouping by ``agent_id`` cancels out the cross-agent race.

    ``agent_id`` alone isn't quite enough: some event kinds (e.g.
    ``context_part_contributed``) don't carry the emitting agent's own id and
    fall back to a shared/default tag, so several real agents' segments can
    land in the same nominal group with no ``agent_id`` left to order by.
    Breaking remaining ties by full normalized content makes the sort — and
    so the comparison in :func:`compare_events_files` — a multiset comparison
    for those runs of same-tagged events, which is exactly what parity
    testing needs (byte-identical content in some order), without discarding
    the meaningful ``agent_id`` grouping everywhere else.
    """
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
    normalized.sort(
        key=lambda e: (e.get("agent_id", ""), e.get("kind", ""), json.dumps(e, sort_keys=True))
    )
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
