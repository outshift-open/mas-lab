#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""One-shot, bounded subagent materialization for workflow engine tools."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from mas.runtime.boundary.context.working_memory_registry import WorkingMemoryRegistry
from mas.runtime.boundary.engine_tools import SubagentContract
from mas.ctl.executor.spawn_ledger import SpawnLedger
from mas.ctl.manifest.spec_bindings import SpecBindingError, parse_subagent_templates
from mas.library.standard.plugins.tools.containment import containment_roots, resolve_under_roots
from mas.runtime.driver.instance import RuntimeInstance
from mas.runtime.engine.tools import spawn_subagent_params

logger = logging.getLogger(__name__)


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
        materialized: Any,
        parent_agent_id: str,
        session_id: str,
        templates: dict[str, SubagentTemplate],
        ledger: SpawnLedger,
        working_memory_registry: WorkingMemoryRegistry,
        display: Any = None,
        verbose: int = 0,
        instance_factory: Callable[[SubagentTemplate, str], RuntimeInstance] | None = None,
        controller_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.materialized = materialized
        self.parent_agent_id = parent_agent_id
        self.session_id = session_id
        self.templates = dict(templates)
        self.ledger = ledger
        self.working_memory_registry = working_memory_registry
        self.display = display
        self.verbose = verbose
        self.instance_factory = instance_factory or self._instantiate
        self.controller_factory = controller_factory

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
        if not self.ledger.allow_spawn(self.session_id, self.parent_agent_id):
            return "[spawn_subagent] blocked: depth or spawn-count budget exceeded"

        child_id = self.ledger.mint_agent_id(self.parent_agent_id, template_id)
        instances = self.materialized.instances
        bus = self.materialized.bus
        instance: RuntimeInstance | None = None
        shared_obs_plugin_set = None
        entered = False
        try:
            instance = self.instance_factory(template, child_id)
            if child_id in instances:
                raise RuntimeError(f"subagent id collision: {child_id}")
            instance.driver.agent_id = child_id
            ctx = getattr(instance.driver, "ctx", None)
            if ctx is not None:
                ctx.session_id = self.session_id
                ctx.agent_id = child_id
            instances[child_id] = instance
            parent_instance = instances.get(self.parent_agent_id)
            shared_obs_plugin_set = getattr(parent_instance, "obs_plugin_set", None)
            if shared_obs_plugin_set is not None and instance.obs_plugin_set is None:
                from mas.runtime.boundary.obs.plugins import attach_observability_plugin_set

                attach_observability_plugin_set(
                    shared_obs_plugin_set,
                    instance,
                    agent_id=child_id,
                    begin_run=False,
                )
            if bus is not None:
                from mas.ctl.placement.bus.adapter import RuntimeCommEndpoint

                bus.register(child_id, RuntimeCommEndpoint(child_id, instance))

            wire_subagent_spawning(
                getattr(instance.driver, "engine", None),
                materialized=self.materialized,
                manifest=template.manifest,
                manifest_dir=template.path.parent,
                parent_agent_id=child_id,
                session_id=self.session_id,
                working_memory_registry=self.working_memory_registry,
                ledger=self.ledger,
                display=self.display,
                verbose=self.verbose,
            )

            from mas.ctl.session.controller import ConversationConfig, SessionController
            from mas.ctl.ui.turn_result import turn_failed

            self.ledger.enter(self.session_id)
            entered = True
            controller_factory = self.controller_factory or SessionController
            controller = controller_factory(
                instance=instance,
                display=self.display,
                verbose=self.verbose,
                agent_id=child_id,
                config=ConversationConfig(single_turn=True),
                session_id=self.session_id,
                working_memory_key=self.session_id,
                working_memory_registry=self.working_memory_registry,
                caller_agent_id=self.parent_agent_id,
            )
            result = controller.run_turn(
                task,
                turn_id=f"{child_id}-spawn",
                parent_call_id=caller_call_id,
            )
            if turn_failed(result):
                return f"[spawn_subagent] {template_id!r} failed"
            return result.text
        except Exception:
            # Exception text can carry absolute paths; keep it out of the parent's context.
            logger.exception("spawn_subagent template %r failed", template_id)
            return f"[spawn_subagent] {template_id!r} failed"
        finally:
            if entered:
                self.ledger.exit(self.session_id)
            if instance is not None:
                if bus is not None:
                    unregister = getattr(bus, "unregister", None)
                    if callable(unregister):
                        unregister(child_id)
                instances.pop(child_id, None)
                self.working_memory_registry.drop(self.session_id, child_id)
                plugin_set = getattr(instance, "obs_plugin_set", None)
                if plugin_set is not None and plugin_set is not shared_obs_plugin_set:
                    plugin_set.close()

    @staticmethod
    def _instantiate(template: SubagentTemplate, child_id: str) -> RuntimeInstance:
        from mas.ctl.session.bootstrap import InstantiationOptions, instantiate_runtime

        instance, _store = instantiate_runtime(
            InstantiationOptions(
                agent_manifest=copy.deepcopy(template.manifest),
                manifest_dir=template.path.parent,
                app_root=template.path.parent,
                enable_observability=True,
            )
        )
        instance.driver.agent_id = child_id
        return instance


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
    spawner = SubagentSpawner(
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