#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Validate that agent prompt versions in a MAS manifest are compatible with a given overlay.

Reads x-compatible-prompt-versions from the overlay metadata and checks each
agent's x-prompt-version in its manifest.

Exit codes:
  0 — all versions compatible (or no constraint declared)
  1 — one or more version mismatches detected
  2 — usage / file error

Usage:
    python validate.py --mas apps/sre-triage/mas.yaml \\
                       --overlay pattern-overlays/centralized-moderator-sre.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _resolve_agent_prompt_version(mas_path: Path, agent_id: str) -> str | None:
    """Return x-prompt-version for agent_id by following its ref from mas.yaml."""
    mas = _load(mas_path)
    agents = (mas.get("spec", {}).get("agency") or {}).get("agents") or []
    for entry in agents:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == agent_id:
            ref = entry.get("ref")
            if not ref:
                return None
            agent_path = (mas_path.parent / ref).resolve()
            if not agent_path.is_file():
                return None
            manifest = _load(agent_path)
            return (manifest.get("metadata") or {}).get("x-prompt-version")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate overlay ↔ agent prompt version compatibility."
    )
    parser.add_argument(
        "--mas",
        required=True,
        type=Path,
        metavar="MAS_YAML",
        help="Path to the MAS manifest (mas.yaml)",
    )
    parser.add_argument(
        "--overlay",
        required=True,
        type=Path,
        metavar="OVERLAY_YAML",
        help="Path to the pattern overlay YAML",
    )
    args = parser.parse_args(argv)

    if not args.mas.is_file():
        print(f"ERROR: MAS manifest not found: {args.mas}", file=sys.stderr)
        return 2
    if not args.overlay.is_file():
        print(f"ERROR: Overlay not found: {args.overlay}", file=sys.stderr)
        return 2

    overlay = _load(args.overlay)
    overlay_name = (overlay.get("metadata") or {}).get("name", args.overlay.name)
    compat = (overlay.get("metadata") or {}).get("x-compatible-prompt-versions")

    if compat is None:
        print(
            f"WARNING: overlay '{overlay_name}' has no x-compatible-prompt-versions — skipping check."
        )
        return 0

    if not compat:
        print(
            f"OK: overlay '{overlay_name}' declares no prompt version constraint (deterministic / self-contained)."
        )
        return 0

    errors: list[str] = []
    for agent_id, accepted in compat.items():
        if not isinstance(accepted, list) or not accepted:
            print(
                f"  SKIP: {agent_id} — accepted list is empty, treating as unconstrained"
            )
            continue
        actual = _resolve_agent_prompt_version(args.mas, agent_id)
        if actual is None:
            errors.append(
                f"  agent '{agent_id}': could not resolve x-prompt-version "
                f"(missing ref or manifest); expected one of {accepted}"
            )
        elif actual not in accepted:
            errors.append(
                f"  agent '{agent_id}': x-prompt-version is '{actual}' "
                f"but overlay '{overlay_name}' requires one of {accepted}"
            )
        else:
            print(f"  OK: {agent_id} @ {actual}")

    if errors:
        print(f"\nERROR: prompt version mismatch for overlay '{overlay_name}':")
        for e in errors:
            print(e)
        return 1

    print(f"\nAll prompt versions compatible with overlay '{overlay_name}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
