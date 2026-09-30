#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Materialize Dataset ``spec.source`` into envelope items (meta-dataset).

The Dataset YAML is a mapping, not a copy of the third-party corpus.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Dict, List


def materialize_source(source: Dict[str, Any], *, base_path: Path) -> List[Dict[str, Any]]:
    """Load an external corpus and map rows onto ``id`` / ``inputs`` / ``expectations``."""
    if not isinstance(source, dict) or not source.get("kind"):
        raise ValueError("spec.source needs kind")
    rows = _load_rows(source, base_path=base_path)
    limit = source.get("limit")
    if limit is not None:
        rows = rows[: int(limit)]
    mapping = source.get("map") or {}
    items = [_map_row(row, mapping, index=i) for i, row in enumerate(rows)]
    return items


def _jsonl_source_loader(source: Dict[str, Any], base_path: Path) -> List[Dict[str, Any]]:
    return _load_jsonl(_resolve_path(source.get("path"), base_path))


def _csv_source_loader(source: Dict[str, Any], base_path: Path) -> List[Dict[str, Any]]:
    return _load_csv(_resolve_path(source.get("path"), base_path))


def _glob_source_loader(source: Dict[str, Any], base_path: Path) -> List[Dict[str, Any]]:
    return _load_glob(str(source.get("path") or ""), base_path)


def _pickle_source_loader(source: Dict[str, Any], base_path: Path) -> List[Dict[str, Any]]:
    return _load_pickle(_resolve_path(source.get("path"), base_path))


def _huggingface_source_loader(source: Dict[str, Any], base_path: Path) -> List[Dict[str, Any]]:
    return _load_huggingface(source)


# Pluggable ``spec.source.kind`` -> loader dispatch. Shared with
# :func:`mas.lab.benchmark.dataset._load_spec_path`, which maps a sidecar
# file's suffix/``format_hint`` onto one of these same kind strings so both
# call sites resolve through this one table instead of two independent
# hand-rolled dispatch chains. Each loader takes ``(source, base_path)`` and
# looks up its own module-level loader by *name* (not a captured reference)
# so tests can still monkeypatch e.g. ``_load_huggingface`` directly.
SOURCE_LOADERS: Dict[str, Callable[[Dict[str, Any], Path], List[Dict[str, Any]]]] = {
    "jsonl": _jsonl_source_loader,
    "csv": _csv_source_loader,
    "glob": _glob_source_loader,
    "pickle": _pickle_source_loader,
    "huggingface": _huggingface_source_loader,
}


def _load_rows(source: Dict[str, Any], *, base_path: Path) -> List[Dict[str, Any]]:
    kind = str(source["kind"])
    loader = SOURCE_LOADERS.get(kind)
    if loader is None:
        raise ValueError(f"unknown spec.source.kind {kind!r}")
    return loader(source, base_path)


def _resolve_path(path_text: Any, base_path: Path) -> Path:
    if not path_text:
        raise ValueError("spec.source.path is required")
    path = Path(str(path_text))
    if not path.is_absolute():
        path = base_path / path
    if not path.is_file():
        raise FileNotFoundError(f"spec.source path not found: {path}")
    return path


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _load_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _load_glob(pattern: str, base_path: Path) -> List[Dict[str, Any]]:
    if not pattern:
        raise ValueError("spec.source.path (glob) is required")
    rows: List[Dict[str, Any]] = []
    for path in sorted(base_path.glob(pattern)):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".jsonl":
            rows.extend(_load_jsonl(path))
            continue
        if path.suffix.lower() == ".csv":
            rows.extend(_load_csv(path))
            continue
        from mas.runtime.spec.source import load_yaml_file

        data = load_yaml_file(path)
        if isinstance(data, list):
            rows.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            rows.append(data)
    return rows


def _load_pickle(path: Path) -> List[Dict[str, Any]]:
    import pickle

    payload = pickle.loads(path.read_bytes())
    if isinstance(payload, list):
        out: List[Dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                out.append(item)
            elif hasattr(item, "__dict__"):
                out.append(dict(vars(item)))
        return out
    raise TypeError(f"pickle dataset must be a list, got {type(payload)}")


def _load_huggingface(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    ds_id = source.get("id")
    if not ds_id:
        raise ValueError("huggingface source needs id (e.g. TIGER-Lab/MMLU-Pro)")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ImportError(
            "spec.source.kind=huggingface requires the 'datasets' package"
        ) from exc
    split = source.get("split") or "validation"
    config = source.get("config") or source.get("name")
    if config:
        dataset = load_dataset(str(ds_id), str(config), split=split)
    else:
        dataset = load_dataset(str(ds_id), split=split)
    if hasattr(dataset, "to_list"):
        rows = dataset.to_list()
        return [dict(row) for row in rows]
    return [dict(row) for row in dataset]


def _row_context(row: Dict[str, Any]) -> Dict[str, Any]:
    ctx = dict(row)
    options = row.get("options")
    if isinstance(options, list):
        ctx.setdefault(
            "options_text",
            "\n".join(f"{chr(65 + i)}. {opt}" for i, opt in enumerate(options)),
        )
    return ctx


def _lookup(spec: Any, ctx: Dict[str, Any]) -> Any:
    """Resolve one mapping *spec* against a row's already-built context.

    *ctx* is the row-invariant :func:`_row_context` result — callers that map
    several ``dest`` keys per row (see :func:`_map_row`) build it once and
    reuse it here instead of recomputing it per lookup.
    """
    if spec is None:
        return None
    if isinstance(spec, dict):
        template = spec.get("template") or spec.get("format")
        if template:
            return str(template).format(**ctx)
        column = spec.get("column") or spec.get("field")
        if column is not None:
            return ctx.get(column)
        return spec
    if isinstance(spec, str):
        if spec in ctx:
            return ctx[spec]
        if "{" in spec and "}" in spec:
            return spec.format(**ctx)
        return ctx.get(spec)
    return spec


def _assign(item: Dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in str(path).split(".") if p]
    if not parts:
        return
    cursor: Any = item
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def _map_row(row: Dict[str, Any], mapping: Dict[str, Any], *, index: int) -> Dict[str, Any]:
    item: Dict[str, Any] = {"id": str(row.get("id") or row.get("question_id") or index)}
    if not mapping:
        user = row.get("question") or row.get("prompt") or row.get("text") or row.get("user")
        if user is None:
            raise ValueError("source row has no question/prompt/text/user and no map")
        item["inputs"] = {"user": user}
        gt = row.get("answer_index", row.get("answer", row.get("ground_truth", row.get("label"))))
        if gt is not None:
            item["expectations"] = {"ground_truth": gt}
        return item
    ctx = _row_context(row)
    for dest, spec in mapping.items():
        _assign(item, str(dest), _lookup(spec, ctx))
    if "id" not in item or item["id"] in (None, ""):
        item["id"] = str(index)
    else:
        item["id"] = str(item["id"])
    if not isinstance(item.get("inputs"), dict) or item["inputs"].get("user") in (None, ""):
        raise ValueError(f"mapped item {item.get('id')!r} missing inputs.user")
    return item
