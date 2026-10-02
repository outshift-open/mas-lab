#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""One-shot, bounded subagent spawn — engine-tool plugin.

Ctl wires ``EngineToolContext`` (materialize / run_turn / teardown). This
class never imports ctl.
"""

from __future__ import annotations

import logging
from typing import Any

from mas.runtime.boundary.engine_tools import EngineToolBudgetExceeded, SubagentContract
from mas.runtime.engine.tools import SPAWN_SUBAGENT_TOOL

logger = logging.getLogger(__name__)


class SubagentSpawner(SubagentContract):
    """Materialize, run, and tear down one pre-authorized template per call."""

    def __init__(
        self,
        *,
        parent_agent_id: str,
        session_id: str,
        templates: dict[str, Any],
        context: Any,
    ) -> None:
        self.parent_agent_id = parent_agent_id
        self.session_id = session_id
        self.templates = dict(templates)
        self.context = context

    def is_subagent_tool(self, tool_name: str) -> bool:
        return tool_name == SPAWN_SUBAGENT_TOOL

    def claims(self, tool_name: str) -> bool:
        return self.is_subagent_tool(tool_name)

    def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str:
        if not self.is_subagent_tool(tool_name):
            return f"[spawn_subagent] unsupported tool {tool_name!r}"
        return self.spawn(
            str(arguments.get("template") or ""),
            str(arguments.get("task") or ""),
            correlation_id=correlation_id,
            caller_call_id=caller_call_id,
        )

    async def acall(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str:
        if not self.is_subagent_tool(tool_name):
            return f"[spawn_subagent] unsupported tool {tool_name!r}"
        return await self.aspawn(
            str(arguments.get("template") or ""),
            str(arguments.get("task") or ""),
            correlation_id=correlation_id,
            caller_call_id=caller_call_id,
        )

    async def aspawn(
        self,
        template_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str:
        template = self.templates.get(template_id)
        if template is None:
            return f"[spawn_subagent] unknown template {template_id!r}"
        task = task.strip()
        if not task:
            return "[spawn_subagent] task must not be empty"
        try:
            child_id = self.context.spawn_instance(
                template.manifest,
                template_id=template_id,
                manifest_dir=template.path.parent,
            )
        except EngineToolBudgetExceeded:
            return "[spawn_subagent] blocked: depth or spawn-count budget exceeded"
        except Exception:
            logger.exception("spawn_subagent template %r could not be materialized", template_id)
            return f"[spawn_subagent] {template_id!r} failed"
        try:
            return await self.context.arun_turn(
                child_id,
                task,
                correlation_id=correlation_id,
                caller_call_id=caller_call_id,
            )
        except Exception:
            logger.exception("spawn_subagent template %r failed", template_id)
            return f"[spawn_subagent] {template_id!r} failed"
        finally:
            self.context.teardown_instance(child_id)

    def spawn(
        self,
        template_id: str,
        task: str,
        *,
        correlation_id: int = 0,
        caller_call_id: str = "",
    ) -> str:
        template = self.templates.get(template_id)
        if template is None:
            return f"[spawn_subagent] unknown template {template_id!r}"
        task = task.strip()
        if not task:
            return "[spawn_subagent] task must not be empty"
        try:
            child_id = self.context.spawn_instance(
                template.manifest,
                template_id=template_id,
                manifest_dir=template.path.parent,
            )
        except EngineToolBudgetExceeded:
            return "[spawn_subagent] blocked: depth or spawn-count budget exceeded"
        except Exception:
            logger.exception("spawn_subagent template %r could not be materialized", template_id)
            return f"[spawn_subagent] {template_id!r} failed"
        try:
            return self.context.run_turn(
                child_id,
                task,
                correlation_id=correlation_id,
                caller_call_id=caller_call_id,
            )
        except Exception:
            # Exception text can carry absolute paths; keep it out of the parent's context.
            logger.exception("spawn_subagent template %r failed", template_id)
            return f"[spawn_subagent] {template_id!r} failed"
        finally:
            self.context.teardown_instance(child_id)
