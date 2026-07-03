#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve spec.context chunks for system-prompt injection."""

from __future__ import annotations

import logging
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


def _safe_is_file(path: Path) -> bool:
    """Return whether path is a regular file, treating overlong names as non-files."""
    try:
        return path.is_file()
    except OSError:
        return False


def resolve_context_chunk(value: Any, *, base_dir: Path) -> str | None:
    """Expand one spec.context entry to prompt text."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        path = (base_dir / text).resolve()
        if _looks_like_path_ref(text) or _safe_is_file(path):
            return _read_context_file(path)
        if _looks_like_bare_path(text):
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


def completion_check_type_from_agent(manifest: dict | None) -> str | None:
    """Return spec.delegation.completion_check when declared on a peer agent."""
    if not manifest:
        return None
    delegation = (manifest.get("spec") or {}).get("delegation") or {}
    if not isinstance(delegation, dict):
        return None
    check = delegation.get("completion_check")
    if isinstance(check, str) and check.strip():
        return check.strip()
    return None
