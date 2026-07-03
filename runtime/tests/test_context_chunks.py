#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for manifest context chunk resolution."""

from pathlib import Path

import pytest

from mas.runtime.boundary.context.chunks import ContextChunkError, resolve_context_chunk


def test_resolve_inline_string():
    assert resolve_context_chunk("hello", base_dir=Path("/tmp")) == "hello"


def test_resolve_ref_dict(tmp_path: Path):
    prompt = tmp_path / "prompts" / "role.md"
    prompt.parent.mkdir()
    prompt.write_text("You are helpful.", encoding="utf-8")
    text = resolve_context_chunk({"ref": "./prompts/role.md"}, base_dir=tmp_path)
    assert text == "You are helpful."


def test_resolve_missing_ref_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_context_chunk({"ref": "./missing.md"}, base_dir=tmp_path)


def test_unsupported_chunk_raises():
    with pytest.raises(ContextChunkError):
        resolve_context_chunk({"nope": True}, base_dir=Path("/tmp"))
