#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unified native events.jsonl verification for pipelines and scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from mas.library.kg.observability.native.validate import (
    EventValidator,
    check_interval_pairing,
    validate_events_json_schema,
)


def verify_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Structural checks on native event dicts."""
    errors: List[str] = []
    warnings: List[str] = []
    stats: Dict[str, Any] = {"total_events": len(events)}

    if not events:
        errors.append("file_not_empty: no events found")
        return {"ok": False, "errors": errors, "warnings": warnings, "stats": stats}

    kinds = {str(e.get("kind", "")) for e in events if e.get("kind")}
    stats["kinds"] = sorted(kinds)
    stats["agents"] = sorted({str(e.get("agent_id", "")) for e in events if e.get("agent_id")})
    run_ids = {str(e.get("run_id", "")) for e in events if e.get("run_id")}
    stats["run_ids"] = sorted(run_ids)
    if len(run_ids) > 1:
        warnings.append(f"single_run: {len(run_ids)} distinct run_id values in one file")

    pairing = check_interval_pairing(events)
    if not pairing.get("ok"):
        warnings.extend(pairing.get("warnings", []))

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
        "pairing": pairing,
    }


def verify_events_file(
    path: Union[str, Path],
    *,
    spec_level: str = "L3",
    spec_path: Optional[str] = None,
    spec_fail_on_error: bool = False,
    spec_strictness: str = "required",
) -> Dict[str, Any]:
    """Load events.jsonl and run full native verification."""
    src = Path(path)
    events: List[Dict[str, Any]] = []
    with src.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{src}:{lineno}: invalid JSON: {exc}") from exc

    report = verify_events(events)
    report["file"] = str(src)

    schema_report = validate_events_json_schema(events)
    report["json_schema"] = schema_report
    if schema_report.get("skipped"):
        # jsonschema isn't installed -- the check never ran. Surfaced as a
        # warning, not folded into "ok": True: a caller that only checks
        # error_count/ok must still be told this check didn't happen.
        report["warnings"].append(f"json_schema_check_skipped: {schema_report.get('reason', '')}")
    elif not schema_report.get("ok"):
        report["errors"].append(f"json_schema: {schema_report.get('error_count', 0)} error(s)")
        for item in schema_report.get("event_errors", [])[:5]:
            report["errors"].append(
                f"  line[{item.get('index')}] ({item.get('kind')}): "
                + "; ".join(item.get("errors", [])[:3])
            )
        report["ok"] = False

    spec_errors: List[str] = []
    strictness = (
        spec_strictness
        if spec_strictness in {"required", "recommended", "complete"}
        else "required"
    )
    validator = EventValidator(spec_path) if spec_path else EventValidator()
    spec_report = validator.validate(events, strictness=strictness)  # type: ignore[arg-type]
    report["eventspec"] = spec_report.summary()
    report["eventspec"]["level_checked"] = spec_level
    report["eventspec"]["strictness"] = strictness
    report["eventspec"]["conformance_at_level"] = spec_report.conformance(spec_level)
    level_errors = spec_report.errors(spec_level)
    if level_errors:
        spec_errors.append(f"eventspec_{spec_level}: {len(level_errors)} error(s)")
        for v in level_errors[:5]:
            spec_errors.append(
                f"  line {v.line} ({v.kind}): {v.message}" + (f" ({v.field})" if v.field else "")
            )

    if spec_errors and spec_fail_on_error:
        report["errors"].extend(spec_errors)
        report["ok"] = False
    elif spec_errors:
        report["warnings"].extend(spec_errors)

    return report
