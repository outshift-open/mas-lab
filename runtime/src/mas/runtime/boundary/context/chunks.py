#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve manifest context chunks (inline text or file refs)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ContextChunkError(ValueError):
    """Raised when a manifest context chunk cannot be resolved."""


def resolve_context_chunk(value: Any, *, base_dir: Path) -> str:
    """Return context text for an inline string or ``{ref: path}`` chunk."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ContextChunkError("context chunk is empty")
        if text.startswith("./") or text.startswith("../"):
            return _read_context_file(base_dir / text)
        return text
    if isinstance(value, dict):
        ref = value.get("ref")
        if isinstance(ref, str) and ref.strip():
            return _read_context_file(base_dir / ref.strip())
    raise ContextChunkError(f"unsupported context chunk value: {value!r}")


def _read_context_file(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"context ref file not found: {resolved}")
    return resolved.read_text(encoding="utf-8").strip()
