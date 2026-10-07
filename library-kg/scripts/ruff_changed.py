#!/usr/bin/env python3
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""Run Ruff incrementally on changed Python files.

Examples:
  python scripts/ruff_changed.py check --base origin/main --head HEAD
  python scripts/ruff_changed.py format-check --base <sha> --head <sha>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def _changed_python_files(base: str, head: str) -> list[str]:
    diff_cmd = [
        "git",
        "diff",
        "--name-only",
        "--diff-filter=ACMRT",
        f"{base}...{head}",
        "--",
        "*.py",
    ]
    result = _run(diff_cmd)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)

    files: list[str] = []
    for raw in result.stdout.splitlines():
        path = raw.strip()
        if not path:
            continue
        if Path(path).is_file():
            files.append(path)
    return sorted(set(files))


def _ruff_command(mode: str, files: list[str]) -> list[str]:
    if mode == "check":
        return [sys.executable, "-m", "ruff", "check", *files]
    if mode == "format-check":
        return [sys.executable, "-m", "ruff", "format", "--check", *files]
    raise ValueError(f"Unsupported mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["check", "format-check"])
    parser.add_argument("--base", default="origin/main", help="Base git ref")
    parser.add_argument("--head", default="HEAD", help="Head git ref")
    args = parser.parse_args(argv)

    files = _changed_python_files(base=args.base, head=args.head)
    if not files:
        print(f"No changed Python files between {args.base} and {args.head}; skipping Ruff.")
        return 0

    cmd = _ruff_command(args.mode, files)
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
