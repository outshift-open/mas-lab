#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Discover tools and skills from a library directory (filesystem scan)."""

from __future__ import annotations

from pathlib import Path

import yaml


def discover_tools(base_dir: Path, namespaces: list[str] | None = None) -> list[dict]:
    """Scan library tree for Tool manifests and ToolProvider infra entries."""
    if not namespaces:
        namespaces = ["global"]

    tools: dict[str, str] = {}

    for ns in namespaces:
        if ns == "global":
            tools_dir = base_dir / "tools"
            if tools_dir.exists():
                for tf in sorted(tools_dir.rglob("*.tool.yaml")):
                    data = yaml.safe_load(tf.read_text(encoding="utf-8"))
                    if (data or {}).get("kind") != "Tool":
                        continue
                    meta = (data or {}).get("metadata", {})
                    name = meta.get("name")
                    if name:
                        tools[f"global/{name}"] = meta.get("description", "")

            infra_dir = base_dir / "infra"
            if infra_dir.exists():
                for infra_file in infra_dir.rglob("*.yaml"):
                    data = yaml.safe_load(infra_file.read_text(encoding="utf-8"))
                    if (data or {}).get("kind") == "ToolProvider":
                        for name in (data or {}).get("spec", {}).get("tools", {}).keys():
                            tools.setdefault(f"global/{name}", "")
        else:
            app_tools_dir = base_dir / "apps" / ns / "tools"
            if app_tools_dir.exists():
                for tf in sorted(app_tools_dir.rglob("*.tool.yaml")):
                    data = yaml.safe_load(tf.read_text(encoding="utf-8"))
                    if (data or {}).get("kind") != "Tool":
                        continue
                    meta = (data or {}).get("metadata", {})
                    name = meta.get("name")
                    if name:
                        tools[name] = meta.get("description", "")

    return sorted(
        [{"name": n, "description": d} for n, d in tools.items()],
        key=lambda t: t["name"],
    )


def discover_skills(base_dir: Path, namespaces: list[str] | None = None) -> list[dict]:
    """Scan library tree for skill folders containing SKILL.md."""
    if not namespaces:
        namespaces = ["global"]

    skills: dict[str, str] = {}

    def _scan_skills_dir(skills_dir: Path, prefix: str) -> None:
        if not skills_dir.exists():
            return
        for skill_path in sorted(skills_dir.iterdir()):
            if not skill_path.is_dir():
                continue
            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue

            content = skill_md.read_text(encoding="utf-8")
            name = skill_path.name
            description = ""

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        frontmatter = yaml.safe_load(parts[1])
                        if frontmatter:
                            name = frontmatter.get("name", name)
                            description = frontmatter.get("description", "").strip()
                    except Exception:
                        pass

            if not description:
                for line in content.splitlines():
                    if line.startswith("# "):
                        description = line[2:].strip()
                        break

            display = f"{prefix}{name}" if prefix else name
            skills.setdefault(display, description)

    for ns in namespaces:
        if ns == "global":
            _scan_skills_dir(base_dir / "skills", "global/")
        else:
            _scan_skills_dir(base_dir / "apps" / ns / "skills", "")

    return sorted(
        [{"name": n, "description": d} for n, d in skills.items()],
        key=lambda s: s["name"],
    )
