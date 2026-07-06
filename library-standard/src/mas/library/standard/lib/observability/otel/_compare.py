#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Structural comparison of OTel span JSONL files (no collector required).

Compares span semantics — span names, ``mas.*`` attribute keys and values
(parent/child topology by span name).  Trace IDs, span IDs, and timestamps
are intentionally ignored (they differ between replay and live export).
Order of spans in the JSONL file is not significant.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _load_spans(path: Path) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                spans.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return spans


def _span_id(span: dict[str, Any]) -> str:
    ctx = span.get("context") or {}
    return str(ctx.get("span_id") or "")


def _parent_id(span: dict[str, Any]) -> str:
    pid = span.get("parent_id")
    if pid:
        return str(pid)
    ctx = span.get("context") or {}
    return str(ctx.get("parent_span_id") or "")


def _mas_attr_keys(span: dict[str, Any]) -> tuple[str, ...]:
    attrs = span.get("attributes") or {}
    return tuple(sorted(k for k in attrs if str(k).startswith("mas.")))


def _mas_attrs(span: dict[str, Any]) -> dict[str, Any]:
    """All mas.* attributes with JSON-normalised values for stable comparison."""
    attrs = span.get("attributes") or {}
    out: dict[str, Any] = {}
    for key in sorted(attrs):
        if not str(key).startswith("mas."):
            continue
        if str(key) == "mas.call.id":
            # Generated or re-scoped per replay run; topology uses span names instead.
            continue
        val = attrs[key]
        if isinstance(val, (dict, list)):
            out[str(key)] = json.dumps(val, sort_keys=True, ensure_ascii=False)
        else:
            out[str(key)] = val
    return out


def _semantic_span_signature(span: dict[str, Any]) -> tuple[str, str]:
    """Order-independent identity: span name + mas.* attribute values."""
    name = str(span.get("name") or "")
    return (name, json.dumps(_mas_attrs(span), sort_keys=True, ensure_ascii=False))


def _mas_value_multiset(spans: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter(_semantic_span_signature(s) for s in spans)


def _span_profile(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a structural profile comparable across replay/live exports."""
    id_to_name: dict[str, str] = {}
    for s in spans:
        sid = _span_id(s)
        if sid:
            id_to_name[sid] = str(s.get("name") or "")

    name_counts: Counter[str] = Counter()
    mas_keys_by_name: dict[str, set[str]] = {}
    edges: Counter[tuple[str, str]] = Counter()
    depths: list[int] = []

    children: dict[str, list[str]] = {}
    for s in spans:
        sid = _span_id(s)
        pid = _parent_id(s)
        if sid and pid:
            children.setdefault(pid, []).append(sid)

    roots = [s for s in spans if not _parent_id(s)]
    warnings: list[str] = []
    if not roots and spans:
        warnings.append(
            "no root spans found (all spans have parents); depth computed from first span"
        )
        roots = [spans[0]]

    def _depth(sid: str, seen: set[str]) -> int:
        if sid in seen:
            return 0
        seen.add(sid)
        child_sids = children.get(sid, [])
        if not child_sids:
            return 1
        return 1 + max(_depth(c, seen) for c in child_sids)

    for s in spans:
        name = str(s.get("name") or "")
        name_counts[name] += 1
        mas_keys_by_name.setdefault(name, set()).update(_mas_attr_keys(s))
        pid = _parent_id(s)
        parent_name = id_to_name.get(pid, "") if pid else ""
        edges[(parent_name, name)] += 1

    for r in roots:
        rid = _span_id(r)
        if rid:
            depths.append(_depth(rid, set()))

    return {
        "span_count": len(spans),
        "name_counts": dict(name_counts),
        "mas_keys_by_name": {k: sorted(v) for k, v in sorted(mas_keys_by_name.items())},
        "edges": {f"{p}->{c}": n for (p, c), n in sorted(edges.items())},
        "max_depth": max(depths) if depths else 0,
        "warnings": warnings,
    }


def _check(
    name: str,
    passed: bool,
    *,
    detail: str = "",
    reference: Any = None,
    candidate: Any = None,
) -> dict[str, Any]:
    return {
        "check": name,
        "passed": passed,
        "detail": detail,
        "reference": reference,
        "candidate": candidate,
    }


def compare_otel_span_sets(
    reference: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    strict: bool = True,
    reference_label: str = "reference",
    candidate_label: str = "candidate",
) -> dict[str, Any]:
    """Compare two in-memory span lists; return a JSON-serialisable report."""
    ref_prof = _span_profile(reference)
    cand_prof = _span_profile(candidate)
    checks: list[dict[str, Any]] = []

    checks.append(
        _check(
            "span_count",
            ref_prof["span_count"] == cand_prof["span_count"],
            detail=f"{reference_label}={ref_prof['span_count']} {candidate_label}={cand_prof['span_count']}",
            reference=ref_prof["span_count"],
            candidate=cand_prof["span_count"],
        )
    )
    checks.append(
        _check(
            "span_name_counts",
            ref_prof["name_counts"] == cand_prof["name_counts"],
            detail="",
            reference=ref_prof["name_counts"],
            candidate=cand_prof["name_counts"],
        )
    )
    checks.append(
        _check(
            "mas_attr_keys_by_name",
            ref_prof["mas_keys_by_name"] == cand_prof["mas_keys_by_name"],
            reference=ref_prof["mas_keys_by_name"],
            candidate=cand_prof["mas_keys_by_name"],
        )
    )
    checks.append(
        _check(
            "topology",
            ref_prof["edges"] == cand_prof["edges"],
            reference=ref_prof["edges"],
            candidate=cand_prof["edges"],
        )
    )
    checks.append(
        _check(
            "max_depth",
            ref_prof["max_depth"] == cand_prof["max_depth"],
            reference=ref_prof["max_depth"],
            candidate=cand_prof["max_depth"],
        )
    )

    ref_values = _mas_value_multiset(reference)
    cand_values = _mas_value_multiset(candidate)
    values_ok = ref_values == cand_values
    value_detail = ""
    if not values_ok:
        missing = ref_values - cand_values
        extra = cand_values - ref_values
        value_detail = (
            f"missing_signatures={sum(missing.values())} "
            f"extra_signatures={sum(extra.values())}"
        )

    def _value_summary(counter: Counter[tuple[str, str]]) -> dict[str, int]:
        by_name: Counter[str] = Counter()
        for (name, _blob), count in counter.items():
            by_name[name] += count
        return dict(sorted(by_name.items()))

    checks.append(
        _check(
            "mas_attr_values",
            values_ok,
            detail=value_detail,
            reference=_value_summary(ref_values),
            candidate=_value_summary(cand_values),
        )
    )

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    ok = passed == total
    all_warnings = ref_prof.get("warnings", []) + cand_prof.get("warnings", [])

    if strict and not ok:
        failed_names = [c["check"] for c in checks if not c["passed"]]
        raise AssertionError(
            f"OTel span comparison failed ({total - passed}/{total} checks): "
            + ", ".join(failed_names)
        )

    report: dict[str, Any] = {
        "passed": ok,
        "reference_label": reference_label,
        "candidate_label": candidate_label,
        "reference_spans": ref_prof["span_count"],
        "candidate_spans": cand_prof["span_count"],
        "checks": checks,
        "summary": {
            "passed": passed,
            "failed": total - passed,
            "total_checks": total,
        },
    }
    if all_warnings:
        report["warnings"] = all_warnings
    return report


def compare_otel_span_files(
    reference_path: Path | str,
    candidate_path: Path | str,
    *,
    strict: bool = True,
    reference_label: str = "reference",
    candidate_label: str = "candidate",
) -> dict[str, Any]:
    """Load two JSONL span files and compare structurally."""
    ref_path = Path(reference_path)
    cand_path = Path(candidate_path)
    ref_spans = _load_spans(ref_path)
    cand_spans = _load_spans(cand_path)
    report = compare_otel_span_sets(
        ref_spans,
        cand_spans,
        strict=strict,
        reference_label=reference_label,
        candidate_label=candidate_label,
    )
    report["reference_file"] = str(ref_path)
    report["candidate_file"] = str(cand_path)
    return report


def compare_otel_span_files_multi(
    reference_path: Path | str,
    candidates: list[tuple[str, Path | str]],
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Compare one reference JSONL against multiple candidate files."""
    ref_path = Path(reference_path)
    ref_spans = _load_spans(ref_path)
    comparisons: list[dict[str, Any]] = []
    all_passed = True
    for label, cand_path in candidates:
        cand_path = Path(cand_path)
        one = compare_otel_span_sets(
            ref_spans,
            _load_spans(cand_path),
            strict=strict,
            reference_label="reference",
            candidate_label=label,
        )
        one["candidate_file"] = str(cand_path)
        comparisons.append(one)
        all_passed = all_passed and one["passed"]

    total_checks = sum(c["summary"]["total_checks"] for c in comparisons)
    passed_checks = sum(c["summary"]["passed"] for c in comparisons)
    return {
        "passed": all_passed,
        "reference_file": str(ref_path),
        "reference_spans": len(ref_spans),
        "comparisons": comparisons,
        "summary": {
            "passed": passed_checks,
            "failed": total_checks - passed_checks,
            "total_checks": total_checks,
            "candidates": len(comparisons),
        },
    }
