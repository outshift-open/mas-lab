#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""CI gate — forbid inlined path/id literals outside constants modules.

Run from repo root:  task verify:literals
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = (
    REPO_ROOT / "runtime" / "src",
    REPO_ROOT / "ctl" / "src",
    REPO_ROOT / "lab" / "components" / "core" / "src",
    REPO_ROOT / "lab" / "components" / "bench" / "src",
    REPO_ROOT / "lab" / "components" / "controller" / "src",
    REPO_ROOT / "lab" / "src",
    REPO_ROOT / "library-standard" / "src",
)

SCHEMA_SCAN_ROOT = REPO_ROOT / "docs" / "schemas"

DOC_SCAN_ROOTS = (
    REPO_ROOT / "docs",
    REPO_ROOT / "lab",
    REPO_ROOT / "labs",
    REPO_ROOT / "runtime" / "docs",
    REPO_ROOT / "docker",
    REPO_ROOT / "library-standard",
)

DOC_ALLOWLIST = {
    REPO_ROOT / "CHANGELOG.md",
}

ALLOWLIST = {
    REPO_ROOT / "runtime" / "src" / "mas" / "runtime" / "constants.py",
    REPO_ROOT / "lab" / "components" / "core" / "src" / "mas" / "lab" / "runners" / "constants.py",
}

SKIP_DIR_NAMES = frozenset({"tests", "__pycache__", ".pytest_cache"})

RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "forbidden-runtime-id",
        re.compile(r"python-v2"),
        "Use DEFAULT_RUNTIME_ID from mas.runtime.constants",
    ),
    (
        "forbidden-legacy-workspace-config",
        re.compile(r"mas-workspace\.yaml"),
        "Use LEGACY_WORKSPACE_CONFIG_FILENAME from mas.runtime.constants (tests only)",
    ),
    (
        "forbidden-legacy-home-path",
        re.compile(r"~/.mas(?:-lab)?"),
        "Use mas.runtime.xdg or mas.lab.paths helpers",
    ),
    (
        "forbidden-home-mas-path",
        re.compile(r"""Path\.home\(\)\s*/\s*["'](?:\.mas(?:-lab)?|\.mas-cache)"""),
        "Use mas.runtime.xdg or mas.lab.paths helpers",
    ),
    (
        "forbidden-runner-id-literal",
        re.compile(r"""runner_id:\s*str\s*=\s*["']mas["']"""),
        "Use DEFAULT_LAB_RUNNER_ID from mas.lab.runners.constants",
    ),
    (
        "inlined-config-filename",
        re.compile(r"""/\s*["']config\.yaml["']"""),
        "Use WORKSPACE_CONFIG_FILENAME from mas.runtime.constants",
    ),
)

SCHEMA_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "forbidden-legacy-home-path",
        re.compile(r"~/.mas(?:-lab)?"),
        "Use XDG path variables — see docs/user-config.md",
    ),
    (
        "forbidden-legacy-workspace-config",
        re.compile(r"mas-workspace\.yaml"),
        "Use config.yaml / LEGACY_WORKSPACE_CONFIG_FILENAME in migration notes only",
    ),
)

DOC_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "forbidden-legacy-home-path",
        re.compile(r"~/.mas(?:-lab)?"),
        "Use $XDG_* / MAS_* variables — see docs/user-config.md",
    ),
)


def _iter_py_files(root: Path):
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.resolve() in ALLOWLIST:
            continue
        yield path


def _iter_schema_files(root: Path):
    if not root.is_dir():
        return
    yield from root.rglob("*.schema.yaml")


def _iter_doc_files(root: Path):
    if not root.is_dir():
        return
    for pattern in ("*.md", "*.yaml", "*.yml"):
        for path in root.rglob(pattern):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved in DOC_ALLOWLIST:
                continue
            if "schemas" in path.parts and path.suffix == ".yaml":
                continue
            yield path


def _scan_file(path: Path, rules: tuple[tuple[str, re.Pattern[str], str], ...], violations: list[str]) -> None:
    rel = path.relative_to(REPO_ROOT)
    text = path.read_text(encoding="utf-8")
    for rule_id, pattern, hint in rules:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{rel}:{line}: [{rule_id}] {hint}")


def main() -> int:
    violations: list[str] = []
    for scan_root in SCAN_ROOTS:
        for path in _iter_py_files(scan_root):
            _scan_file(path, RULES, violations)
    for path in _iter_schema_files(SCHEMA_SCAN_ROOT):
        _scan_file(path, SCHEMA_RULES, violations)
    for scan_root in DOC_SCAN_ROOTS:
        for path in _iter_doc_files(scan_root):
            _scan_file(path, DOC_RULES, violations)

    if violations:
        print("Forbidden literals found (use constants / xdg / paths instead):\n", file=sys.stderr)
        for item in sorted(violations):
            print(f"  {item}", file=sys.stderr)
        print(f"\n{len(violations)} violation(s).", file=sys.stderr)
        return 1

    print("check_literals: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
