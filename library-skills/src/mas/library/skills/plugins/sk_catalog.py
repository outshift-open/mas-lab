#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""SkillCatalogPlugin — ContextContract context source for the SYSTEM_SKILLS band.

Progressive disclosure — tier 1: catalog + behavioral instruction.
Full bodies loaded on-demand via activate_skill (tier 2).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agentskills import Discovery, SkillRecord, SkillRegistry, skill_refs_from_manifest
from agentskills.lifecycle import SkillSessionState
from mas.runtime.contracts.context_contract import (
    ContextContract,
    ContextPart,
)

from .skill_plugin_registry import SkillImplementation, SkillPluginRegistry

logger = logging.getLogger(__name__)

_BEHAVIORAL_INSTRUCTION = (
    "When a task matches a skill's description, call `activate_skill(name)` "
    "to load its full instructions before proceeding. "
    "Resolve relative paths in skill instructions against the skill's directory "
    "using `read_skill_file(skill, path)`."
)


class SkillCatalogPlugin(ContextContract):
    """Injects the skill catalog into SYSTEM_SKILLS."""

    def __init__(
        self,
        manifest: dict | None = None,
        base_dir: Path | None = None,
        *,
        impl: SkillImplementation | str = SkillImplementation.NATIVE,
    ) -> None:
        super().__init__()
        self.impl = _coerce_impl(impl)
        self._registry = SkillRegistry()
        self._backend_plugin: Any | None = None
        self._catalog_text: str = ""
        if manifest and base_dir:
            self._build(manifest, base_dir)

    @property
    def registry(self) -> SkillRegistry:
        """Skill registry shared with SkillToolsPlugin."""
        return self._registry

    @property
    def backend_plugin(self) -> Any | None:
        """Selected backend plugin instance (for non-native adapters)."""
        return self._backend_plugin

    def collect_context(self) -> list[ContextPart]:
        """Return catalog ContextPart for SYSTEM_SKILLS."""
        if not self._catalog_text:
            return []
        return [ContextPart.skills(self._catalog_text, source="skills", section_id="skills/catalog")]

    def _build(self, manifest: dict, base_dir: Path) -> None:
        """Build catalog using agentskills.Discovery."""
        refs = skill_refs_from_manifest(manifest)
        if not refs:
            return

        if self.impl is not SkillImplementation.NATIVE:
            self._build_from_selected_impl(refs=refs, base_dir=base_dir)
            return

        discovery = Discovery(
            manifest_skills=refs,
            base_dir=base_dir,
            client_name="mas-lab",
        )
        discovered_registry = discovery.discover()

        for record in discovered_registry.all():
            self._registry.register(record)

        records = self._registry.all()
        if not records:
            return

        lines: list[str] = [
            "## Available Skills",
            "",
            _BEHAVIORAL_INSTRUCTION,
            "",
        ]
        for rec in records:
            lines.append(f"- **{rec.name}**: {rec.description}")
        self._catalog_text = "\n".join(lines)
        logger.debug(
            "SkillCatalogPlugin: built catalog with %d skill(s): %s",
            len(records),
            [r.name for r in records],
        )

    def _build_from_selected_impl(self, refs: list[str], base_dir: Path) -> None:
        """Build catalog through selected SkillPlugin backend.

        Backends discover available skills; we keep only entries referenced by
        ``spec.skills`` to preserve the contract that the manifest controls
        which skills are visible to the model.
        """
        plugin = SkillPluginRegistry(impl=self.impl).get_plugin(base_dir=base_dir)
        discovered = plugin.discover(base_dir)
        selected_names = _declared_skill_names(refs)

        for name, meta in discovered.items():
            if selected_names and not _matches_declared_name(name, selected_names):
                continue
            skill_md = meta.path if meta.path.name == "SKILL.md" else (meta.path / "SKILL.md")
            self._registry.register(
                SkillRecord(
                    name=name,
                    description=meta.description,
                    path=skill_md,
                    compatibility=meta.compatibility,
                    license=meta.license,
                    allowed_tools=tuple(meta.allowed_tools or ()),
                )
            )

        self._backend_plugin = plugin
        records = self._registry.all()
        if not records:
            return

        lines: list[str] = [
            "## Available Skills",
            "",
            _BEHAVIORAL_INSTRUCTION,
            "",
        ]
        for rec in records:
            lines.append(f"- **{rec.name}**: {rec.description}")
        self._catalog_text = "\n".join(lines)
        logger.debug(
            "SkillCatalogPlugin(%s): built catalog with %d skill(s): %s",
            self.impl.value,
            len(records),
            [r.name for r in records],
        )


class ActivatedSkillsContextPlugin(ContextContract):
    """Emits activated skill bodies as pinned SYSTEM_SKILLS ContextParts."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[ContextPart] = []

    def add_activated(self, name: str, body: str) -> None:
        """Called by SkillToolsPlugin after first activation."""
        if any(p.section_id == f"skills/activated/{name}" for p in self._parts):
            return
        self._parts.append(
            ContextPart.skills(
                content=f'<activated_skill name="{name}">\n{body}\n</activated_skill>',
                source=f"skills/{name}",
                section_id=f"skills/activated/{name}",
                priority=41 + len(self._parts),
            )
        )

    def collect_context(self) -> list[ContextPart]:
        """Return all activated skill bodies as pinned ContextParts."""
        return list(self._parts)


def attach_skill_catalog_plugin(
    ctx: Any,
    manifest: dict | None,
    base_dir: Path | None,
    *,
    impl: SkillImplementation | str = SkillImplementation.NATIVE,
) -> SkillCatalogPlugin | None:
    """Build and attach SkillCatalogPlugin to ctx."""
    if not manifest or not base_dir:
        return None
    if not skill_refs_from_manifest(manifest):
        return None

    plugin = SkillCatalogPlugin(manifest=manifest, base_dir=base_dir, impl=impl)
    if not plugin.registry:
        return None

    from mas.runtime.boundary.context.plugin_collection import PluginCollection

    collection = getattr(ctx, "plugin_collection", None)
    if collection is None:
        ctx.plugin_collection = PluginCollection()
        collection = ctx.plugin_collection
    collection.register(plugin)

    activated_plugin = ActivatedSkillsContextPlugin()
    collection.register(activated_plugin)
    ctx.activated_skills_plugin = activated_plugin
    ctx.skill_registry = plugin.registry
    if plugin.backend_plugin is not None:
        ctx.skill_backend_plugin = plugin.backend_plugin

    if not getattr(ctx, "skill_session_state", None):
        ctx.skill_session_state = SkillSessionState()

    return plugin


def _coerce_impl(impl: SkillImplementation | str) -> SkillImplementation:
    if isinstance(impl, SkillImplementation):
        return impl
    try:
        return SkillImplementation(str(impl).strip().lower())
    except ValueError:
        logger.warning("Unknown skill implementation %r; defaulting to native", impl)
        return SkillImplementation.NATIVE


def _declared_skill_names(refs: list[str]) -> set[str]:
    names: set[str] = set()
    for ref in refs:
        raw = str(ref).strip()
        if not raw or raw.startswith("@"):
            continue
        leaf = raw.split("/", 1)[-1]
        names.add(leaf)
        names.add(leaf.replace("-", "_"))
        names.add(leaf.replace("_", "-"))
    return names


def _matches_declared_name(name: str, selected: set[str]) -> bool:
    return (
        name in selected
        or name.replace("-", "_") in selected
        or name.replace("_", "-") in selected
    )
