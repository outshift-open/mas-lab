#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS Lab integration adapter for skill plugins.

Adapts SkillPlugin interface to MAS Lab's ContextContract and ToolContract.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mas.runtime.contracts.context_contract import ContextContract, ContextPart
from mas.runtime.contracts.tool_contract import ToolContract

from .skill_plugin_registry import SkillImplementation, SkillPluginRegistry

if TYPE_CHECKING:
    from .skill_plugin_base import SkillPlugin

logger = logging.getLogger(__name__)


class SkillPluginContextAdapter(ContextContract):
    """Adapts a SkillPlugin to MAS Lab ContextContract.

    Discovers skills and emits as SYSTEM_SKILLS context.
    """

    def __init__(
        self,
        impl: SkillImplementation | str = SkillImplementation.NATIVE,
        base_dir: Path | None = None,
    ):
        self.impl = impl
        self.base_dir = base_dir or Path.cwd()
        self._plugin = None
        self._catalog = None

    def _get_plugin(self) -> SkillPlugin:
        if self._plugin is None:
            registry = SkillPluginRegistry(impl=self.impl)
            self._plugin = registry.get_plugin(base_dir=self.base_dir)
        return self._plugin

    def _build(self, context: dict) -> None:
        """Discover skills on first build."""
        plugin = self._get_plugin()
        self._catalog = plugin.discover(self.base_dir)
        logger.info(f"[{self.impl}] Discovered {len(self._catalog)} skills")

    def collect_context(self) -> list[ContextPart]:
        """Emit Tier 1 metadata as SYSTEM_SKILLS context."""
        if self._catalog is None:
            self._build({})

        # Format catalog for LLM context
        lines = ["## Available Skills (Plugin: {})".format(self.impl)]
        lines.append("")

        for name, meta in sorted(self._catalog.items()):
            lines.append(f"- **{name}**: {meta.description}")
            if meta.compatibility:
                lines.append(f"  - Compatibility: {meta.compatibility}")

        content = "\n".join(lines)

        return [
            ContextPart(
                role="SYSTEM_SKILLS",
                content=content,
                pinned=True,
            )
        ]


class SkillPluginToolAdapter(ToolContract):
    """Adapts a SkillPlugin to MAS Lab ToolContract.

    Provides tools: activate_skill, list_skill_files, read_skill_file, run_skill_script.
    """

    def __init__(
        self,
        impl: SkillImplementation | str = SkillImplementation.NATIVE,
        base_dir: Path | None = None,
    ):
        self.impl = impl
        self.base_dir = base_dir or Path.cwd()
        self._plugin = None
        self._catalog = None

    def _get_plugin(self) -> SkillPlugin:
        if self._plugin is None:
            registry = SkillPluginRegistry(impl=self.impl)
            self._plugin = registry.get_plugin(base_dir=self.base_dir)
        return self._plugin

    def _build(self, context: dict) -> None:
        """Discover skills on first build."""
        plugin = self._get_plugin()
        self._catalog = plugin.discover(self.base_dir)

    def _activate_skill(self, skill_name: str) -> dict:
        """Tier 2: Activate skill and return full instructions."""
        if self._catalog is None:
            self._build({})

        plugin = self._get_plugin()
        activation = plugin.activate(skill_name)

        return {
            "name": activation.name,
            "instructions": activation.body,
            "resources": {k: str(v) for k, v in activation.resources.items()},
        }

    def _list_skill_files(self, skill_name: str) -> dict:
        """List files in skill directory."""
        if self._catalog is None:
            self._build({})

        meta = self._catalog.get(skill_name)
        if not meta:
            return {"error": f"Skill not found: {skill_name}"}

        files = {
            "scripts": [],
            "references": [],
            "assets": [],
        }

        for category in files:
            subdir = meta.path / category
            if subdir.exists():
                for file in subdir.rglob("*"):
                    if file.is_file():
                        rel = str(file.relative_to(meta.path))
                        files[category].append(rel)

        return files

    def _read_skill_file(self, skill_name: str, resource_path: str) -> dict:
        """Tier 3: Read a skill resource."""
        if self._catalog is None:
            self._build({})

        plugin = self._get_plugin()
        content = plugin.read_resource(skill_name, resource_path)

        return {
            "skill": skill_name,
            "path": resource_path,
            "content": content,
        }

    def _run_skill_script(
        self,
        skill_name: str,
        script_name: str,
        args: list[str] | None = None,
        timeout: int = 30,
        env_extra: dict[str, str] | None = None,
    ) -> dict:
        """Execute skill script."""
        if self._catalog is None:
            self._build({})

        plugin = self._get_plugin()
        result = plugin.run_script(
            skill_name=skill_name,
            script_name=script_name,
            args=args or [],
            timeout=timeout,
            env_extra=env_extra or {},
        )

        return {
            "skill": skill_name,
            "script": script_name,
            "exit_code": result["exit_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "success": result["ok"],
        }

    def _get_tools(self) -> dict:
        """Register tools."""
        return {
            "activate_skill": {
                "description": "Activate a skill and get its full instructions",
                "schema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of skill to activate",
                        }
                    },
                    "required": ["skill_name"],
                },
                "func": self._activate_skill,
            },
            "list_skill_files": {
                "description": "List files in a skill directory",
                "schema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of skill",
                        }
                    },
                    "required": ["skill_name"],
                },
                "func": self._list_skill_files,
            },
            "read_skill_file": {
                "description": "Read a resource file from a skill",
                "schema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of skill",
                        },
                        "resource_path": {
                            "type": "string",
                            "description": "Path to resource (e.g., 'scripts/main.py')",
                        },
                    },
                    "required": ["skill_name", "resource_path"],
                },
                "func": self._read_skill_file,
            },
            "run_skill_script": {
                "description": "Execute a skill script",
                "schema": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of skill",
                        },
                        "script_name": {
                            "type": "string",
                            "description": "Script filename (no path separators)",
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Command-line arguments",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Max execution time (seconds)",
                            "default": 30,
                        },
                        "env_extra": {
                            "type": "object",
                            "description": "Additional environment variables",
                        },
                    },
                    "required": ["skill_name", "script_name"],
                },
                "func": self._run_skill_script,
            },
        }
