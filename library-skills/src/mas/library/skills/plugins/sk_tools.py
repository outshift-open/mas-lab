#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""SkillToolsPlugin — ToolContract for model-driven skill activation.

FSM placement
-------------
These tools fire on the ``tool_execute`` FSM symbol (the stochastic path,
§6.2 of the product model) when the model decides to call one of:

  activate_skill(name)           — load full SKILL.md body (tier 2)
  list_skill_files(skill)        — enumerate bundled resources
  read_skill_file(skill, path)   — read a specific resource file

The plugin gets ``ctx`` (AutoCtxAssembler) passed at call time and reads
``ctx.skill_registry`` (a SkillRegistry populated by SkillCatalogPlugin) to
look up skill paths.  No shared mutable state between calls.

Security
--------
``read_skill_file`` resolves paths under the skill's base directory and
rejects any path that escapes it (directory traversal guard).

Progressive disclosure — tier 2 / tier 3
-----------------------------------------
``activate_skill`` returns the SKILL.md body (frontmatter stripped) wrapped
in ``<skill_content>`` tags, plus a ``<skill_resources>`` listing of bundled
scripts/references/assets — but does NOT eagerly load them (tier 3 is loaded
on-demand by the model via ``read_skill_file``).

See: https://agentskills.io/client-implementation/adding-skills-support#step-4
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agentskills import SkillRegistry, parse_skill_frontmatter
from agentskills.lifecycle import SkillSessionState
from mas.runtime.contracts.tool_contract import ToolContract

from .skill_plugin_base import require_str_arg
from .skill_plugin_registry import SkillImplementation, SkillPluginRegistry

logger = logging.getLogger(__name__)

_RESOURCE_DIRS = ("scripts", "references", "assets")


class SkillToolsPlugin(ToolContract):
    """ToolContract providing activate_skill, list_skill_files, read_skill_file.

    Loaded once per agent session by ManifestToolProvider (via the YAML ref in
    ``spec.tools``).  The registry is read from ``ctx.skill_registry`` at each
    tool call — no constructor dependency on bootstrap ordering.

    When constructed with an explicit ``registry``, ``list_tools()`` includes
    the valid skill names in the ``activate_skill`` tool description, helping
    the model avoid hallucinating nonexistent skill names.
    """

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        impl: SkillImplementation | str = SkillImplementation.NATIVE,
        base_dir: str | Path | None = None,
    ) -> None:
        super().__init__()
        self._static_registry = registry  # optional: populated by tests or direct use
        self._impl = _coerce_impl(impl)
        self._base_dir = Path(base_dir).resolve() if base_dir else None
        self._local_backend_plugin: Any | None = None

    # ------------------------------------------------------------------
    # ToolContract — list_tools and dispatch
    # ------------------------------------------------------------------

    def list_tools(
        self,
        registry: SkillRegistry | None = None,
        activated: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        # Build a dynamic description and optional enum including valid skill names.
        # `registry` (from ctx.skill_registry, the live per-session registry --
        # see on_collect_tools) takes priority over the constructor-time
        # `_static_registry`, which the real model-facing tool path never sets
        # (skill-access.tool.yaml constructs this class with no arguments and
        # reads ctx.skill_registry per-call instead -- see on_execute_tool).
        reg = registry if registry is not None else self._static_registry
        if reg:
            valid = reg.names()
            # Exclude already-activated skills from the enum whenever at least
            # one skill still isn't activated. This is what actually stops a
            # forced tool_choice (llm_tool_choice) from making the model pick
            # the same already-activated name on every forced round -- a
            # schema-level guarantee instead of hoping the model reads the
            # "already_activated" notice in a prior tool result and moves on.
            # Falls back to the full list once everything is activated (an
            # empty enum is invalid, and forcing has already stopped by then).
            if activated:
                remaining = [n for n in valid if n not in activated]
                valid = remaining or valid
            name_hint = f" Valid names: {valid}." if valid else ""
        else:
            valid = []
            name_hint = ""

        name_schema: dict[str, Any] = {
            "type": "string",
            "description": "Skill name as listed in the catalog.",
        }
        if valid:
            name_schema["enum"] = valid  # constrain to known skill names

        return [
            {
                "name": "activate_skill",
                "description": (
                    "Load the full instructions for a named skill. "
                    "Call this when the task matches a skill listed in the catalog. "
                    "Returns the skill body and lists bundled resource files."
                    f"{name_hint}"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"name": name_schema},
                    "required": ["name"],
                },
            },
            {
                "name": "list_skill_files",
                "description": (
                    "List all files inside a skill's directory "
                    "(references, scripts, assets, etc.). "
                    "Use to discover supporting resources before reading them."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string", "description": "Skill name."},
                    },
                    "required": ["skill"],
                },
            },
            {
                "name": "read_skill_file",
                "description": (
                    "Read a file from a skill's directory. "
                    "Path is relative to the skill directory "
                    "(e.g. 'references/rules.md', 'scripts/lint.py'). "
                    "Use after activate_skill lists resources in <skill_resources>."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string", "description": "Skill name."},
                        "path": {
                            "type": "string",
                            "description": "Relative path within the skill directory.",
                        },
                    },
                    "required": ["skill", "path"],
                },
            },
        ]

    def on_execute_tool(
        self, tool_name: str, arguments: dict[str, Any], **kwargs: Any
    ) -> Any:
        """Route to the appropriate handler; extract ctx from kwargs."""
        ctx = kwargs.get("ctx")
        registry = _registry_from_ctx(ctx)

        try:
            if tool_name == "activate_skill":
                return self._activate_skill(require_str_arg(arguments, "name"), registry, ctx=ctx)
            if tool_name == "list_skill_files":
                return self._list_skill_files(require_str_arg(arguments, "skill"), registry, ctx=ctx)
            if tool_name == "read_skill_file":
                return self._read_skill_file(
                    require_str_arg(arguments, "skill"),
                    require_str_arg(arguments, "path"),
                    registry,
                    ctx=ctx,
                )
        except TypeError as exc:
            return {"error": str(exc)}
        return None  # not our tool

    def on_collect_tools(self, *, ctx: Any = None, **_: Any) -> list[dict[str, Any]]:
        # Prefer the live per-session registry (see ManifestToolProvider.list_tools's
        # ctx threading) over the constructor-time _static_registry -- this is what
        # gives activate_skill's "name" parameter a real enum constraint in the
        # actual model-facing tool path (skill-access.tool.yaml never sets
        # _static_registry). Without it, the model has no schema-level guard
        # against a name that doesn't exactly match a registered skill.
        ctx_registry = _registry_from_ctx(ctx)
        reg = ctx_registry if ctx_registry is not None else self._static_registry
        # Don't register tools when no skills available (agentskills.io Step 3 §Filtering)
        if reg is not None and not reg:  # registry present but empty
            return []
        session = getattr(ctx, "skill_session_state", None)
        activated = set(session.activated_names()) if session is not None else None
        return self.list_tools(reg, activated=activated)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _activate_skill(self, name: str, registry: SkillRegistry | None, ctx: Any = None) -> dict[str, Any]:
        """Tier-2 progressive disclosure: return body + resource listing.

        Deduplication (agentskills.io Step 5):
        If the skill has already been activated this session, return a compact
        notice instead of re-loading the full body.  This prevents duplicate
        skill instructions from accumulating in the conversation context.
        """
        if not name:
            return {"error": "name is required"}

        record = registry.get(name) if registry else None
        if record is None:
            available = registry.names() if registry else []
            return {
                "error": (
                    f"Skill {name!r} not found in registry. "
                    f"Available: {available}"
                )
            }

        backend_plugin = _backend_plugin_from_ctx(
            ctx,
            impl=self._impl,
            base_dir=self._base_dir,
            local_cache=self,
        )

        # Deduplication — check session state.
        #
        # NOTE: dedup is only possible when `ctx.skill_session_state` is set
        # (populated by SkillCatalogPlugin during bootstrap). If it's None
        # (e.g. this plugin is exercised standalone/in a test without the
        # full context stack), this check is a no-op and `activate_skill`
        # will re-return the full body on every call — this is intentional
        # graceful degradation, not a bug, since without session state there
        # is nowhere to record "already activated" across calls anyway.
        session: SkillSessionState | None = getattr(ctx, "skill_session_state", None)
        if session is not None and session.is_activated(name):
            session.note_reactivation_attempt(name)
            rec = session.get(name)
            turn_info = f" (activated at turn {rec.turn})" if rec and rec.turn else ""
            logger.debug("activate_skill(%r): already in session context — skipping re-load", name)
            return {
                "notice": (
                    f"Skill '{name}' instructions are already in context{turn_info}. "
                    "Refer to the earlier tool result for the full instructions."
                ),
                "skill": name,
                "already_activated": True,
            }

        resources: list[str] = []
        if backend_plugin is not None:
            try:
                activation = backend_plugin.activate(name)
            except Exception as exc:
                return {"error": f"Cannot activate skill {name!r}: {exc}"}
            body = activation.body
            resources = sorted(str(r) for r in activation.resources.keys())
        else:
            try:
                raw = record.path.read_text(encoding="utf-8")
            except OSError as exc:
                return {"error": f"Cannot read skill {name!r}: {exc}"}

            _meta, body = parse_skill_frontmatter(raw)

            # Enumerate bundled resources (tier 3 — listed but not yet loaded)
            for sub in _RESOURCE_DIRS:
                sub_dir = record.base_dir / sub
                if sub_dir.is_dir():
                    for f in sorted(sub_dir.iterdir()):
                        if f.is_file():
                            resources.append(f"{sub}/{f.name}")
            for f in sorted(record.base_dir.iterdir()):
                if f.is_file() and f.name != "SKILL.md":
                    rel = f.name
                    if rel not in resources:
                        resources.append(rel)

        content_parts = [f'<skill_content name="{name}">', body]
        if resources:
            content_parts.append("\n<skill_resources>")
            for r in resources:
                content_parts.append(f"  <file>{r}</file>")
            content_parts.append("</skill_resources>")
        content_parts.append(f"\nSkill directory: {record.base_dir}")
        content_parts.append("</skill_content>")

        content = "\n".join(content_parts)

        # Mark as activated in session state
        if session is not None:
            turn = getattr(ctx, "turn_index", 0) or 0
            session.mark_activated(name, turn=turn)
            logger.debug("activate_skill(%r): activated at turn %d", name, turn)

        # Register body in ActivatedSkillsContextPlugin for compaction protection
        activated_plugin = getattr(ctx, "activated_skills_plugin", None)
        if activated_plugin is not None:
            try:
                activated_plugin.add_activated(name, body)
            except Exception:  # pragma: no cover
                pass  # never block activation on compaction-protection failure

        result: dict[str, Any] = {
            "content": content,
            "skill": name,
            "base_dir": str(record.base_dir),
        }
        # Include compatibility note so the model can check environment requirements
        if record.compatibility:
            result["compatibility"] = record.compatibility
        return result

    def _list_skill_files(
        self,
        skill: str,
        registry: SkillRegistry | None,
        *,
        ctx: Any = None,
    ) -> dict[str, Any]:
        """List all files inside the skill's directory."""
        if not skill:
            return {"error": "skill is required"}

        record = registry.get(skill) if registry else None
        if record is None:
            return {"error": f"Skill {skill!r} not found"}

        backend_plugin = _backend_plugin_from_ctx(
            ctx,
            impl=self._impl,
            base_dir=self._base_dir,
            local_cache=self,
        )
        if backend_plugin is not None:
            try:
                activation = backend_plugin.activate(skill)
            except Exception as exc:
                return {"error": f"Cannot list resources for {skill!r}: {exc}"}
            files = sorted(str(r) for r in activation.resources.keys())
            return {"skill": skill, "files": files, "base_dir": str(record.base_dir)}

        files: list[str] = []
        try:
            for f in sorted(record.base_dir.rglob("*")):
                if f.is_file() and f.name != "SKILL.md":
                    try:
                        files.append(str(f.relative_to(record.base_dir)))
                    except ValueError:
                        pass
        except OSError as exc:
            return {"error": f"Cannot list skill directory: {exc}"}

        return {"skill": skill, "files": files, "base_dir": str(record.base_dir)}

    def _read_skill_file(
        self,
        skill: str,
        path: str,
        registry: SkillRegistry | None,
        *,
        ctx: Any = None,
    ) -> dict[str, Any]:
        """Read a file from the skill's directory (directory-traversal safe)."""
        if not skill:
            return {"error": "skill is required"}
        if not path:
            return {"error": "path is required"}

        record = registry.get(skill) if registry else None
        if record is None:
            return {"error": f"Skill {skill!r} not found"}

        backend_plugin = _backend_plugin_from_ctx(
            ctx,
            impl=self._impl,
            base_dir=self._base_dir,
            local_cache=self,
        )
        if backend_plugin is not None:
            try:
                content = backend_plugin.read_resource(skill, path)
            except Exception as exc:
                return {"error": f"Cannot read {path!r}: {exc}"}
            return {"skill": skill, "path": path, "content": content}

        base = record.base_dir.resolve()
        target = (base / path).resolve()

        # Security: reject any path that escapes the skill directory
        try:
            target.relative_to(base)
        except ValueError:
            return {"error": f"Path {path!r} escapes the skill directory — access denied"}

        if not target.is_file():
            return {"error": f"File {path!r} not found in skill {skill!r}"}

        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {"error": f"Cannot read {path!r}: {exc}"}

        return {"skill": skill, "path": path, "content": content}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _registry_from_ctx(ctx: Any) -> SkillRegistry | None:
    """Extract SkillRegistry from the assembly context object, if present."""
    return getattr(ctx, "skill_registry", None)


def _coerce_impl(impl: SkillImplementation | str) -> SkillImplementation:
    if isinstance(impl, SkillImplementation):
        return impl
    try:
        return SkillImplementation(str(impl).strip().lower())
    except ValueError:
        logger.warning("Unknown skill implementation %r; defaulting to native", impl)
        return SkillImplementation.NATIVE


def _backend_plugin_from_ctx(
    ctx: Any,
    *,
    impl: SkillImplementation,
    base_dir: Path | None,
    local_cache: SkillToolsPlugin,
) -> Any | None:
    plugin = getattr(ctx, "skill_backend_plugin", None) if ctx is not None else None
    if plugin is not None:
        return plugin
    if impl is SkillImplementation.NATIVE:
        return None
    if local_cache._local_backend_plugin is None:
        resolved_base = (base_dir or Path.cwd()).resolve()
        plugin = SkillPluginRegistry(impl=impl).get_plugin(base_dir=resolved_base)
        plugin.discover(resolved_base)
        local_cache._local_backend_plugin = plugin
    return local_cache._local_backend_plugin
