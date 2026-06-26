#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Verify relative markdown links in OSS documentation trees."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#")

# Paths scanned for release-quality link hygiene.
DOC_ROOTS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs",
    REPO_ROOT / "lab" / "README.md",
    REPO_ROOT / "lab" / "docs",
    REPO_ROOT / "lab" / "components" / "bench" / "README.md",
    REPO_ROOT / "labs" / "README.md",
    REPO_ROOT / "labs" / "extensions.lab" / "README.md",
    REPO_ROOT / "library-standard" / "docs",
]


def _markdown_files() -> list[Path]:
    files: list[Path] = []
    for root in DOC_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            for path in sorted(root.rglob("*.md")):
                files.append(path)
    return files


def _resolve_link(source: Path, raw: str) -> Path | None:
    target = raw.split("#")[0].strip()
    if not target or any(target.startswith(p) for p in SKIP_PREFIX):
        return None
    return (source.parent / target).resolve()


def _broken_links() -> list[tuple[str, str, str]]:
    missing: list[tuple[str, str, str]] = []
    for md in _markdown_files():
        text = md.read_text(encoding="utf-8", errors="replace")
        for match in LINK_RE.finditer(text):
            raw = match.group(1)
            resolved = _resolve_link(md, raw)
            if resolved is None:
                continue
            if not resolved.exists():
                rel_src = str(md.relative_to(REPO_ROOT))
                try:
                    rel_tgt = str(resolved.relative_to(REPO_ROOT))
                except ValueError:
                    rel_tgt = str(resolved)
                missing.append((rel_src, raw, rel_tgt))
    return missing


def test_oss_documentation_has_no_broken_relative_links() -> None:
    broken = _broken_links()
    if not broken:
        return
    lines = ["Broken relative markdown links:"]
    for src, raw, tgt in broken:
        lines.append(f"  {src}")
        lines.append(f"    [{raw}] -> {tgt}")
    pytest.fail("\n".join(lines))
