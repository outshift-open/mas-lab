#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""One-shot, bounded subagent materialization for workflow engine tools."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from mas.ctl.executor.engine_tool_context import MaterializedEngineToolContext
from mas.runtime.boundary.context.working_memory_registry import WorkingMemoryRegistry
from mas.ctl.executor.spawn_ledger import SpawnLedger
from mas.ctl.manifest.spec_bindings import SpecBindingError, parse_subagent_templates
from mas.library.standard.plugins.tools.containment import containment_roots, resolve_under_roots
from mas.runtime.boundary.engine_tools import EngineToolBudgetExceeded, SubagentContract
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.engine.tools import spawn_subagent_params

logger = logging.getLogger(__name__)


def _resolve_engine_tool_class(name: str, fallback: type) -> type:
    """Resolve an ``engine_tool_provider`` variant, falling back when unregistered."""
    from mas.runtime.registry import get_registry

    variant = get_registry().resolve_by_type("engine_tool_provider", name)
    if variant is None:
        logger.debug("engine_tool_provider %r not registered; using %s", name, fallback.__name__)
        return fallback
    return variant.load_class()


@dataclass(frozen=True)
class SubagentTemplate:
    """Validated local agent manifest selected by a spawning tool call."""

    template_id: str
    description: str
    path: Path
    manifest: dict[str, Any]


def load_subagent_templates(
    manifest: dict[str, Any],
    manifest_dir: Path | None,
) -> dict[str, SubagentTemplate]:
    """Resolve and validate template refs within the manifest's allowed roots."""
    raw_templates = (spawn_subagent_params(manifest.get("spec")) or {}).get("templates")
    try:
        rows = parse_subagent_templates(raw_templates)
    except SpecBindingError as exc:
        raise ValueError(str(exc)) from exc
    if not rows:
        return {}
    if manifest_dir is None:
        raise ValueError("manifest_dir is required when spawn_subagent templates are declared")

    from mas.ctl.validate import validate_file
    from mas.ctl.manifest.spec_bindings import validate_agent_spec_bindings

    base_dir = Path(manifest_dir).resolve()
    roots = containment_roots(base_dir, base_dir)
    templates: dict[str, SubagentTemplate] = {}
    for row in rows:
        template_id = row["id"]
        path = resolve_under_roots(base_dir, row["ref"], containment_roots=roots)
        if not path.is_file():
            raise FileNotFoundError(f"subagent template {template_id!r} not found: {path}")
        template_manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(template_manifest, dict):
            raise ValueError(f"subagent template {template_id!r} must be a manifest object")
        validate_file(path, kind="agent").raise_if_failed()
        validate_agent_spec_bindings(template_manifest.get("spec") or {})
        templates[template_id] = SubagentTemplate(
            template_id=template_id,
            description=row.get("description") or "",
            path=path,
            manifest=template_manifest,
        )
    return templates


class SubagentSpawner(SubagentContract):
    """Materialize, run, and tear down one pre-authorized template per call."""

    def __init__(
        self,
        *,
        materialized: Any = None,
        parent_agent_id: str,
        session_id: str,
        templates: dict[str, SubagentTemplate],
        ledger: SpawnLedger,
        working_memory_registry: WorkingMemoryRegistry,
        display: Any = None,
        verbose: int = 0,
        instance_factory: Callable[[SubagentTemplate, str], RuntimeInstance] | None = None,
        controller_factory: Callable[..., Any] | None = None,
        context: Any = None,
    ) -> None:
        self.parent_agent_id = parent_agent_id
        self.session_id = session_id
        self.templates = dict(templates)
        self.ledger = ledger
        self.working_memory_registry = working_memory_registry
        self.display = display
        self.verbose = verbose
        self.context = context or MaterializedEngineToolContext(
            materialized=materialized,
            session_id=session_id,
            parent_agent_id=parent_agent_id,
            ledger=ledger,
            working_memory_registry=working_memory_registry,
            display=display,
            verbose=verbose,
            instance_factory=self._adapt_instance_factory(instance_factory),
            controller_factory=controller_factory,
        )

    def _adapt_instance_factory(
        self, legacy: Callable[[SubagentTemplate, str], RuntimeInstance] | None
    ) -> Callable[..., RuntimeInstance] | None:
        """Keep the template-shaped factory seam the spawner's own tests use."""
        if legacy is None:
            return None

        def factory(_manifest: Any, _manifest_dir: Any, child_id: str, template_id: str) -> RuntimeInstance:
            return legacy(self.templates[template_id], child_id)

        return factory

    def is_subagent_tool(self, tool_name: str) -> bool:
        return tool_name == "spawn_subagent"

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


def wire_subagent_spawning(
    engine: Any,
    *,
    materialized: Any,
    manifest: dict[str, Any],
    manifest_dir: Path | None,
    parent_agent_id: str,
    session_id: str,
    working_memory_registry: WorkingMemoryRegistry | None = None,
    ledger: SpawnLedger | None = None,
    display: Any = None,
    verbose: int = 0,
    instance_factory: Callable[[SubagentTemplate, str], RuntimeInstance] | None = None,
    controller_factory: Callable[..., Any] | None = None,
) -> SubagentSpawner | None:
    """Attach the spawner contract only when the tools entry declares it."""
    spec = manifest.get("spec") or {}
    params = spawn_subagent_params(spec)
    if params is None:
        return None
    templates = load_subagent_templates(manifest, manifest_dir)
    if not templates:
        raise ValueError("spawn_subagent requires at least one entry in params.templates")

    if working_memory_registry is None:
        working_memory_registry = getattr(materialized, "_session_working_memory_registry", None)
        if working_memory_registry is None:
            working_memory_registry = WorkingMemoryRegistry()
            materialized._session_working_memory_registry = working_memory_registry
    if ledger is None:
        ledger = getattr(materialized, "_subagent_spawn_ledger", None)
        if ledger is None:
            ledger = SpawnLedger(
                max_depth=params.get("max_depth", 3),
                max_spawns=params.get("max_spawns", 8),
            )
            materialized._subagent_spawn_ledger = ledger

    from mas.runtime.engine.leaf import leaf_engine

    leaf = leaf_engine(engine)
    for existing in getattr(leaf, "engine_tool_contracts", ()) or ():
        if isinstance(existing, SubagentSpawner) and existing.parent_agent_id == parent_agent_id:
            return existing
    spawner = _resolve_engine_tool_class("spawn_subagent", SubagentSpawner)(
        materialized=materialized,
        parent_agent_id=parent_agent_id,
        session_id=session_id,
        templates=templates,
        ledger=ledger,
        working_memory_registry=working_memory_registry,
        display=display,
        verbose=verbose,
        instance_factory=instance_factory,
        controller_factory=controller_factory,
    )
    contracts = list(getattr(leaf, "engine_tool_contracts", ()) or ())
    contracts.append(spawner)
    leaf.engine_tool_contracts = tuple(contracts)
    return spawner