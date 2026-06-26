#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Apply or verify Cisco Apache-2.0 SPDX file headers across the repository.

Canonical header (comment syntax varies by file type)::

    Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
    SPDX-License-Identifier: Apache-2.0

Usage::

    python scripts/apply_license_headers.py              # dry-run summary
    python scripts/apply_license_headers.py --write      # apply changes
    python scripts/apply_license_headers.py --check      # exit 1 if not compliant

Prefer SPDX + short copyright over pasting the full Apache 2.0 boilerplate in every
file when LICENSE exists at the repo root (REUSE / Apache-2.0 best practice).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

COPYRIGHT_LINE = "Copyright (c) 2026 Cisco Systems, Inc. and its affiliates"
SPDX_LINE = "SPDX-License-Identifier: Apache-2.0"
CANONICAL_LINES = (COPYRIGHT_LINE, SPDX_LINE)

# Directories that are never scanned (build outputs, vendored deps, caches).
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "htmlcov",
        ".eggs",
        "egg-info",
        "site-packages",
        "target",
        "vendor",
        "third-party",
        "third_party",
    }
)

SKIP_DIR_SUFFIXES = (".egg-info",)

# Basenames never headered (legal artefacts, locks, generated markers).
SKIP_BASENAMES = frozenset(
    {
        "LICENSE",
        "LICENSE.txt",
        "LICENSE.md",
        "NOTICE",
        "CHANGELOG",
        "CHANGELOG.md",
        "yarn.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "poetry.lock",
        "go.sum",
        ".gitkeep",
        ".gitignore",
        ".dockerignore",
        ".cursorignore",
        ".prettierignore",
        ".eslintignore",
    }
)

# Extensions: source / human-authored text we header.
HASH_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyx",
        ".pxd",
        ".pxi",
        ".sh",
        ".bash",
        ".zsh",
        ".yaml",
        ".yml",
        ".toml",
        ".sql",
        ".rb",
        ".rake",
        ".pl",
        ".pm",
        ".r",
        ".cmake",
        ".dockerfile",
        ".graphql",
        ".proto",
        ".conf",
    }
)

SLASH_EXTENSIONS = frozenset(
    {
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".mjs",
        ".cjs",
        ".mts",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".kts",
        ".swift",
        ".scala",
        ".cs",
        ".cpp",
        ".cc",
        ".cxx",
        ".c",
        ".h",
        ".hpp",
        ".hh",
        ".glsl",
    }
)

BLOCK_STAR_EXTENSIONS = frozenset({".css", ".scss", ".less"})

HTML_COMMENT_EXTENSIONS = frozenset({".html", ".htm", ".xml", ".svg", ".md", ".mdx"})

HASH_BASENAMES = frozenset(
    {
        "dockerfile",
        "makefile",
        "gnumakefile",
        "cmakelists.txt",
    }
)

# Data, media, binaries — do not header.
SKIP_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".mp4",
        ".wav",
        ".mp3",
        ".zip",
        ".gz",
        ".tar",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".bin",
        ".dat",
        ".npy",
        ".npz",
        ".pkl",
        ".pickle",
        ".parquet",
        ".feather",
        ".arrow",
        ".sqlite",
        ".db",
        ".lock",
        ".sum",
        ".mod",
        ".snap",
        ".sha256",
        ".csv",
        ".jsonl",
        ".json",
        ".txt",
        ".log",
        ".min.js",
        ".map",
        ".wasm",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".jar",
        ".class",
        ".pyc",
        ".pyo",
        ".whl",
        ".egg",
        ".tag",
    }
)

LICENSE_MARKERS = re.compile(
    r"(copyright|spdx-license-identifier|apache license,\s*version|"
    r"licensed under the apache|http://www\.apache\.org/licenses/)",
    re.IGNORECASE,
)

COPYRIGHT_CISCO = re.compile(r"copyright.*cisco", re.IGNORECASE)
SPDX_APACHE = re.compile(r"spdx-license-identifier:\s*apache-2\.0", re.IGNORECASE)


@dataclass(frozen=True)
class CommentStyle:
    name: str


HASH = CommentStyle("hash")
SLASH = CommentStyle("slash")
BLOCK = CommentStyle("block")
HTML = CommentStyle("html")


def should_skip_dir(path: Path) -> bool:
    name = path.name
    if name in SKIP_DIR_NAMES:
        return True
    if name.startswith(".venv"):
        return True
    return any(name.endswith(suffix) for suffix in SKIP_DIR_SUFFIXES)


def should_skip_path(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return True
    for part in rel_parts[:-1]:
        if should_skip_dir(Path(part)):
            return True
    return False


def comment_style_for(path: Path) -> CommentStyle | None:
    base = path.name.lower()
    if base in SKIP_BASENAMES:
        return None
    if base in HASH_BASENAMES or base.startswith("dockerfile"):
        return HASH
    ext = path.suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return None
    if ext in HASH_EXTENSIONS:
        return HASH
    if ext in SLASH_EXTENSIONS:
        return SLASH
    if ext in BLOCK_STAR_EXTENSIONS:
        return BLOCK
    if ext in HTML_COMMENT_EXTENSIONS:
        return HTML
    return None


def format_header(style: CommentStyle) -> str:
    if style == HASH:
        return "\n".join(f"#  {line}" for line in CANONICAL_LINES) + "\n\n"
    if style == SLASH:
        return "\n".join(f"//  {line}" for line in CANONICAL_LINES) + "\n\n"
    if style == BLOCK:
        body = "\n".join(f" * {line}" for line in CANONICAL_LINES)
        return f"/*\n{body}\n */\n\n"
    if style == HTML:
        body = "\n".join(f"  {line}" for line in CANONICAL_LINES)
        return f"<!--\n{body}\n-->\n\n"
    raise ValueError(style)


def _strip_comment_content(line: str, style: CommentStyle) -> str:
    s = line.strip()
    if style == HASH:
        if s.startswith("#"):
            return s.lstrip("#").strip()
    if style == SLASH:
        if s.startswith("//"):
            return s[2:].strip()
    if style == BLOCK:
        s = s.strip()
        if s.startswith("/*"):
            s = s[2:]
        if s.endswith("*/"):
            s = s[:-2]
        if s.startswith("*"):
            s = s[1:]
        return s.strip()
    if style == HTML:
        s = s.strip()
        if s.startswith("<!--"):
            s = s[4:]
        if s.endswith("-->"):
            s = s[:-3]
        return s.strip()
    return s


def _line_is_comment_or_blank(line: str, style: CommentStyle) -> bool:
    s = line.strip()
    if not s:
        return True
    if style == HASH:
        return s.startswith("#")
    if style == SLASH:
        return s.startswith("//")
    if style == BLOCK:
        return s.startswith("/*") or s.startswith("*") or s.endswith("*/")
    if style == HTML:
        return s.startswith("<!--") or s.endswith("-->") or (s.startswith("<!--") and "-->" in s)
    return False


def _looks_like_license_text(text: str) -> bool:
    return bool(LICENSE_MARKERS.search(text))


def _canonical_from_comments(comment_lines: list[str], style: CommentStyle) -> tuple[str, ...] | None:
    stripped = [_strip_comment_content(ln, style) for ln in comment_lines if ln.strip()]
    non_empty = [s for s in stripped if s]
    if not non_empty:
        return None
    has_spdx = any(SPDX_APACHE.search(s) for s in non_empty)
    has_copy = any(COPYRIGHT_CISCO.search(s) for s in non_empty)
    if not (has_spdx or has_copy or _looks_like_license_text(" ".join(non_empty))):
        return None
    return tuple(non_empty)


def _header_matches_canonical(comment_lines: list[str], style: CommentStyle) -> bool:
    parsed = _canonical_from_comments(comment_lines, style)
    if parsed is None:
        return False
    joined = "\n".join(parsed)
    return COPYRIGHT_CISCO.search(joined) and SPDX_APACHE.search(joined)


def _leading_preamble(lines: list[str]) -> int:
    """Return index after shebang, XML declaration, and PEP 263 encoding line."""
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#!"):
        idx += 1
    if idx < len(lines) and lines[idx].strip().startswith("<?xml"):
        idx += 1
    if idx < len(lines):
        enc = lines[idx].strip()
        if enc.startswith("#") and "coding" in enc and "utf-8" in enc.lower():
            idx += 1
    return idx


def _consume_block_comment(lines: list[str], start: int, style: CommentStyle) -> int:
    if style == BLOCK:
        if not lines[start].strip().startswith("/*"):
            return start
        i = start
        while i < len(lines):
            if "*/" in lines[i]:
                return i + 1
            i += 1
        return i
    if style == HTML:
        line = lines[start].strip()
        if line.startswith("<!--") and line.endswith("-->"):
            return start + 1
        if not line.startswith("<!--"):
            return start
        i = start
        while i < len(lines):
            if "-->" in lines[i]:
                return i + 1
            i += 1
        return i
    return start


def find_license_region(lines: list[str], style: CommentStyle, start: int) -> tuple[int, int]:
    """Return (header_start, header_end) for an existing license block, or (start, start)."""
    i = start
    if i >= len(lines):
        return start, start

    i = _consume_block_comment(lines, i, style)
    if i > start:
        block = lines[start:i]
        if _canonical_from_comments(block, style) is not None:
            return start, i
        # Block was not a license — treat as no header
        return start, start

    if not _line_is_comment_or_blank(lines[i], style):
        return start, start

    header_start = i
    while i < len(lines) and _line_is_comment_or_blank(lines[i], style):
        content = _strip_comment_content(lines[i], style)
        if content and not _looks_like_license_text(content) and not COPYRIGHT_CISCO.search(content):
            # Comment block that isn't license-related (e.g. file description) — stop
            if i == header_start:
                return start, start
            break
        i += 1
        # Stop after license block ends (blank line after comments)
        if i < len(lines) and not lines[i - 1].strip() and i > header_start:
            break

    block = lines[header_start:i]
    if _canonical_from_comments(block, style) is None:
        return start, start
    return header_start, i


def find_all_license_regions(
    lines: list[str], style: CommentStyle, start: int
) -> list[tuple[int, int]]:
    """Find every license-like comment block at or after *start*."""
    regions: list[tuple[int, int]] = []
    i = start
    n = len(lines)
    while i < n:
        hs, he = find_license_region(lines, style, i)
        if hs == he:
            i += 1
            continue
        regions.append((hs, he))
        i = he if he > hs else i + 1
    return regions


def _line_has_license_marker(line: str, style: CommentStyle) -> bool:
    if not _line_is_comment_or_blank(line, style):
        return False
    content = _strip_comment_content(line, style)
    if not content:
        return False
    return bool(
        COPYRIGHT_CISCO.search(content)
        or SPDX_APACHE.search(content)
        or _looks_like_license_text(content)
    )


def _scan_inline_license_markers(
    lines: list[str], style: CommentStyle, *, after: int
) -> list[int]:
    """Line numbers (1-based) of license markers after index *after*."""
    hits: list[int] = []
    for i in range(after, len(lines)):
        if _line_has_license_marker(lines[i], style):
            hits.append(i + 1)
    return hits


@dataclass(frozen=True)
class AuditResult:
    status: str  # ok | missing | incompatible | duplicate | binary | unreadable
    detail: str = ""


def audit_content(text: str, style: CommentStyle) -> AuditResult:
    if not text:
        return AuditResult("missing", "empty file")

    lines = text.splitlines()
    preamble_end = _leading_preamble(lines)
    regions = find_all_license_regions(lines, style, preamble_end)

    if not regions:
        return AuditResult("missing", "no license header at file start")

    first_start, first_end = regions[0]
    first_block = lines[first_start:first_end]

    issues: list[str] = []

    if first_start != preamble_end:
        issues.append(
            f"header not at expected line {preamble_end + 1} (found at {first_start + 1})"
        )

    if not _header_matches_canonical(first_block, style):
        parsed = _canonical_from_comments(first_block, style)
        if parsed is None:
            issues.append("license-like block is not canonical SPDX header")
        else:
            issues.append(f"non-canonical header: {' | '.join(parsed[:3])}")

    if len(regions) > 1:
        extra = ", ".join(str(s + 1) for s, _ in regions[1:])
        issues.append(f"multiple license blocks (extra at lines {extra})")

    inline = _scan_inline_license_markers(lines, style, after=first_end)
    if inline:
        issues.append(
            "duplicate license markers later in file at lines "
            + ", ".join(str(n) for n in inline[:5])
            + (" …" if len(inline) > 5 else "")
        )

    if issues:
        if any("multiple" in x or "duplicate" in x for x in issues):
            return AuditResult("duplicate", "; ".join(issues))
        if any("non-canonical" in x or "not canonical" in x for x in issues):
            return AuditResult("incompatible", "; ".join(issues))
        return AuditResult("incompatible", "; ".join(issues))

    return AuditResult("ok")


def audit_file(path: Path) -> AuditResult:
    style = comment_style_for(path)
    if style is None:
        return AuditResult("ok", "excluded by policy")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return AuditResult("binary", "not utf-8 text")
    except OSError as exc:
        return AuditResult("unreadable", str(exc))
    return audit_content(text, style)


def run_audit(root: Path, *, scopes: list[Path] | None = None) -> dict[str, list[tuple[str, str]]]:
    grouped: dict[str, list[tuple[str, str]]] = {
        "ok": [],
        "missing": [],
        "incompatible": [],
        "duplicate": [],
        "binary": [],
        "unreadable": [],
    }
    for path in iter_target_files(root, scopes=scopes):
        rel = str(path.relative_to(root))
        result = audit_file(path)
        grouped.setdefault(result.status, []).append((rel, result.detail))
    return grouped


def build_new_content(text: str, style: CommentStyle) -> tuple[str, str]:
    """Return (new_text, action) where action is skip|ok|update|add."""
    if not text:
        return format_header(style), "add"

    raw_lines = text.splitlines()
    preamble_end = _leading_preamble(raw_lines)

    header_start, header_end = find_license_region(raw_lines, style, preamble_end)
    header_block = raw_lines[header_start:header_end]

    if header_block and _header_matches_canonical(header_block, style):
        return text, "ok"

    new_header_lines = format_header(style).rstrip("\n").splitlines()
    body_lines = raw_lines[header_end:] if header_end > header_start else raw_lines[preamble_end:]

    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)

    assembled: list[str] = []
    assembled.extend(raw_lines[:preamble_end])
    assembled.extend(new_header_lines)
    assembled.extend(body_lines)

    new_text = "\n".join(assembled)
    if text.endswith("\n") or not assembled:
        new_text += "\n"

    if header_block:
        return new_text, "update"
    return new_text, "add"


def iter_target_files(root: Path, *, scopes: list[Path] | None = None) -> list[Path]:
    roots = scopes if scopes else [root]
    out: list[Path] = []
    for base in roots:
        base = base.resolve()
        if base.is_file():
            if not should_skip_path(base, root) and comment_style_for(base) is not None:
                out.append(base)
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if should_skip_path(path, root):
                continue
            if comment_style_for(path) is None:
                continue
            out.append(path)
    return sorted(set(out))


def process_file(path: Path, *, write: bool) -> str:
    style = comment_style_for(path)
    assert style is not None
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "binary"

    new_text, action = build_new_content(original, style)
    if action == "ok":
        return "ok"
    if action == "binary":
        return "binary"
    if write:
        path.write_text(new_text, encoding="utf-8", newline="\n")
    return action


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply headers (default is dry-run)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Report missing, incompatible, and duplicate headers (no writes)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any file is missing or has a non-canonical header",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: parent of scripts/)",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional paths under the repo to scan (default: entire repository)",
    )
    args = parser.parse_args()

    if args.write and args.check:
        print("Use only one of --write or --check", file=sys.stderr)
        return 2
    if args.audit and args.write:
        print("Use only one of --audit or --write", file=sys.stderr)
        return 2

    root = args.root.resolve()
    scopes = None
    if args.paths:
        scopes = [(root / p).resolve() if not p.is_absolute() else p.resolve() for p in args.paths]

    if args.audit:
        grouped = run_audit(root, scopes=scopes)
        for status in ("missing", "incompatible", "duplicate", "binary", "unreadable"):
            items = grouped.get(status, [])
            if not items:
                continue
            print(f"\n== {status.upper()} ({len(items)}) ==")
            for rel, detail in items[:200]:
                suffix = f" — {detail}" if detail else ""
                print(f"  {rel}{suffix}")
            if len(items) > 200:
                print(f"  … and {len(items) - 200} more")
        print(
            f"\nAudit summary: ok={len(grouped.get('ok', []))} "
            f"missing={len(grouped.get('missing', []))} "
            f"incompatible={len(grouped.get('incompatible', []))} "
            f"duplicate={len(grouped.get('duplicate', []))} "
            f"binary={len(grouped.get('binary', []))}"
        )
        problems = (
            grouped.get("missing", [])
            + grouped.get("incompatible", [])
            + grouped.get("duplicate", [])
        )
        return 1 if problems else 0

    counts: dict[str, int] = {}
    problems: list[str] = []

    for path in iter_target_files(root, scopes=scopes):
        rel = path.relative_to(root)
        result = process_file(path, write=args.write)
        counts[result] = counts.get(result, 0) + 1
        if result in ("add", "update"):
            problems.append(str(rel))
            prefix = "would " if not args.write else ""
            print(f"{prefix}{result}: {rel}")

    print(
        f"\nSummary: ok={counts.get('ok', 0)} "
        f"add={counts.get('add', 0)} update={counts.get('update', 0)} "
        f"binary={counts.get('binary', 0)}"
    )

    if args.check and problems:
        print(f"\n{len(problems)} file(s) need license headers.", file=sys.stderr)
        return 1
    if not args.write and not args.check and problems:
        print("\nDry run — re-run with --write to apply.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
