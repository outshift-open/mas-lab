#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Skill plugin registry — select and manage multiple implementations."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .skill_plugin_base import SkillPlugin

logger = logging.getLogger(__name__)


class SkillImplementation(str, Enum):
    """Available skill implementations."""

    NATIVE = "native"  # python-agentskills + python-sandbox (baseline)
    LANGCHAIN = "langchain"  # deepagents (LangGraph) — https://pypi.org/project/deepagents/
    ADK = "adk"  # Google Agent Development Kit


class SkillPluginRegistry:
    """Registry for selecting skill implementations.

    Usage:
        # Select implementation
        registry = SkillPluginRegistry(impl=SkillImplementation.LANGCHAIN)
        plugin = registry.get_plugin(base_dir=Path("skills/"))

        # Discover & activate
        skills = plugin.discover(Path("skills/"))
        activation = plugin.activate("my-skill")
        result = plugin.run_script("my-skill", "main.py", args=["arg1"])
    """

    _IMPLEMENTATIONS = {
        SkillImplementation.NATIVE: "plugin_skills_native",
        SkillImplementation.LANGCHAIN: "plugin_skills_langchain",
        SkillImplementation.ADK: "plugin_skills_adk",
    }

    _CLASS_NAMES = {
        SkillImplementation.NATIVE: "NativeSkillPlugin",
        SkillImplementation.LANGCHAIN: "LangChainSkillPlugin",
        SkillImplementation.ADK: "ADKSkillPlugin",
    }

    def __init__(self, impl: SkillImplementation | str = SkillImplementation.NATIVE):
        if isinstance(impl, str):
            impl = SkillImplementation(impl)
        self.impl = impl
    def get_plugin(
        self,
        base_dir: Path | None = None,
        working_dir: Path | None = None,
        run_dir: Path | None = None,
    ) -> SkillPlugin:
        """Load and instantiate the selected plugin.

        Args:
            base_dir: Root directory for skill discovery.
            working_dir: Explicit working directory override (legacy).
            run_dir: Run output directory.  When provided the plugin creates
                its scratch files under ``run_dir/tmp/skills-scratch/``,
                co-located with ``traces/`` and ``checkpoints/``.
                Pass the ``output_dir`` from the benchmark runner here.

        Returns:
            SkillPlugin instance.
        """
        module_name = self._IMPLEMENTATIONS.get(self.impl)
        class_name = self._CLASS_NAMES.get(self.impl)

        if not module_name or not class_name:
            msg = f"Unknown implementation: {self.impl}"
            raise ValueError(msg)

        try:
            module = __import__(
                f"mas.library.skills.plugins.{module_name}",
                fromlist=[class_name],
            )
            plugin_class = getattr(module, class_name)
            return plugin_class(base_dir=base_dir, working_dir=working_dir, run_dir=run_dir)
        except ImportError as e:
            msg = f"Failed to load {self.impl} plugin: {e}"
            logger.error(msg)
            raise ImportError(msg) from e

    @classmethod
    def available_implementations(cls) -> list[str]:
        """List available implementations."""
        return [impl.value for impl in SkillImplementation]

    def __repr__(self) -> str:
        return f"SkillPluginRegistry(impl={self.impl.value})"
