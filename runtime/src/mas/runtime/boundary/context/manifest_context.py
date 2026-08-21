#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve spec.context chunks for system-prompt injection."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ContextChunkError(ValueError):
    """Raised when a manifest context chunk cannot be resolved."""


class ContextRefNotFoundError(FileNotFoundError):
    """Raised when a spec.context file ref does not exist on disk."""


def routing_description_from_agent(manifest: dict | None) -> str | None:
    """Machine-facing delegate / registry description."""
    if not manifest:
        return None
    spec = manifest.get("spec") or {}
    desc = spec.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    return None


def _read_context_file(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ContextRefNotFoundError(f"context ref file not found: {resolved}")
    return resolved.read_text(encoding="utf-8").strip()


def _looks_like_path_ref(text: str) -> bool:
    return text.startswith("./") or text.startswith("../")


def _looks_like_bare_path(text: str) -> bool:
    return "/" in text or text.endswith((".md", ".yaml", ".yml", ".txt"))


def _is_probeable_path_candidate(text: str) -> bool:
    """Single-line values short enough to be relative file refs under base_dir."""
    return "\n" not in text and len(text) <= 512


def resolve_context_chunk(value: Any, *, base_dir: Path) -> str | None:
    """Expand one spec.context entry to prompt text.

    A list value is a sequence of fragments (each itself a string or {ref}),
    resolved individually and joined with newlines -- lets a chunk be composed
    from multiple pieces (e.g. a base fragment plus one an overlay appended via
    merge_context_chunk) instead of one monolithic string.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if _looks_like_path_ref(text):
            return _read_context_file((base_dir / text).resolve())
        if _is_probeable_path_candidate(text) and _looks_like_bare_path(text):
            path = (base_dir / text).resolve()
            try:
                if path.is_file():
                    return _read_context_file(path)
            except OSError:
                pass
            logger.warning(
                "context chunk %r looks like a file path but was not found under %s; "
                "treating as inline text",
                text,
                base_dir,
            )
        return text
    if isinstance(value, dict):
        ref = value.get("ref")
        if isinstance(ref, str) and ref.strip():
            return _read_context_file((base_dir / ref.strip()).resolve())
    elif isinstance(value, list):
        fragments: list[str] = []
        for item in value:
            if isinstance(item, list):
                raise ContextChunkError(
                    f"unsupported context chunk value: nested array {item!r}"
                )
            text = resolve_context_chunk(item, base_dir=base_dir)
            if text:
                fragments.append(text)
        return "\n".join(fragments) if fragments else None
    raise ContextChunkError(f"unsupported context chunk value: {value!r}")


def context_chunks_from_spec(spec: dict[str, Any], *, base_dir: Path) -> list[str]:
    """Return [key] content lines for all resolved spec.context entries."""
    context = spec.get("context") or {}
    if not isinstance(context, dict):
        return []
    out: list[str] = []
    for key, val in context.items():
        try:
            text = resolve_context_chunk(val, base_dir=base_dir)
        except ContextChunkError as exc:
            logger.warning("skipping context key %r: %s", key, exc)
            continue
        if text:
            out.append(f"[{key}] {text}")
    return out


_CONTEXT_CHUNK_OP_KEYS = {"replace", "add", "remove", "clear"}


def _context_chunk_ops(value: Any) -> dict[str, Any] | None:
    """Recognize the `{"$op": {...}}` (or bare) sugar form on a chunk patch value."""
    if isinstance(value, dict) and isinstance(value.get("$op"), dict):
        value = value["$op"]
    if not isinstance(value, dict):
        return None
    if not (set(value) & _CONTEXT_CHUNK_OP_KEYS):
        return None
    return value


def _as_fragment_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def merge_context_chunk(existing: Any, incoming: Any) -> Any:
    """Merge one spec.context.<key> overlay patch value onto its base value.

    A plain value (string/{ref}/list) fully replaces the base chunk -- implicit
    replace ergonomics, consistent with every other overlay merge strategy in
    this repo. A `{"$op": {replace|add|remove|clear}}` value instead operates on
    the base chunk's fragment list (coercing a scalar base value to a one-item
    list first), so an overlay can add or remove a single fragment -- e.g.
    append one sentence to spec.context.role -- without restating the rest.
    """
    ops = _context_chunk_ops(incoming)
    if ops is None:
        return deepcopy(incoming)

    result = [] if ops.get("clear") is True else _as_fragment_list(existing)

    if "replace" in ops:
        result = list(ops.get("replace") or [])

    if "remove" in ops:
        to_remove = list(ops.get("remove") or [])
        result = [item for item in result if item not in to_remove]

    if "add" in ops:
        for item in list(ops.get("add") or []):
            if item not in result:
                result.append(item)

    return result


def merge_context_map(existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge an overlay's spec.context patch onto the base spec.context map."""
    merged = deepcopy(existing) if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if value is None:
            merged.pop(key, None)
            continue
        merged[key] = merge_context_chunk(merged.get(key), value)
    return merged
