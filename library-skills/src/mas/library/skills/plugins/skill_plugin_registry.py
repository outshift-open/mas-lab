#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Select a ``skill_impl`` plugin through ``PluginRegistry``.

``skill_impl`` entries live in ``library-skills/library.yaml``. A fourth
implementation is a new catalog row, not a second hardcoded dict.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from mas.runtime.registry import get_registry

if TYPE_CHECKING:
    from .skill_plugin_base import SkillPlugin

logger = logging.getLogger(__name__)

_DEFAULT_IMPL = "native"


def coerce_skill_impl(impl: object | None, *, default: str = _DEFAULT_IMPL) -> str:
    """Normalize a skill_impl name. Unknown names stay as given (callers decide)."""
    value = getattr(impl, "value", impl)
    name = str(value if value is not None else default).strip().lower()
    return name or default


class SkillPluginRegistry:
    """Facade over ``PluginRegistry`` for ``skill_impl`` construction.

    Usage:
        registry = SkillPluginRegistry(impl="langchain")
        plugin = registry.get_plugin(base_dir=Path("skills/"))
    """

    def __init__(self, impl: object | None = _DEFAULT_IMPL):
        self.impl = coerce_skill_impl(impl)
        known = {n.lower() for n in self.available_implementations()}
        if known and self.impl not in known:
            raise ValueError(f"Unknown implementation: {self.impl}")

    def get_plugin(
        self,
        base_dir: Path | None = None,
        working_dir: Path | None = None,
        run_dir: Path | None = None,
    ) -> SkillPlugin:
        """Instantiate the selected ``skill_impl`` via the process registry."""
        variant = get_registry().resolve_by_type("skill_impl", self.impl)
        if variant is None:
            raise ValueError(f"Unknown implementation: {self.impl}")
        plugin_class = variant.load_class()
        return plugin_class(base_dir=base_dir, working_dir=working_dir, run_dir=run_dir)

    @classmethod
    def available_implementations(cls) -> list[str]:
        """List ``skill_impl`` names registered in ``PluginRegistry``."""
        return get_registry().list_names("skill_impl")

    def __repr__(self) -> str:
        return f"SkillPluginRegistry(impl={self.impl!r})"
