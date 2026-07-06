#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""
Pipeline executor with automatic dependency resolution and caching.
"""


import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]
from datetime import datetime

from mas.lab.benchmark.pipeline import Pipeline, PipelineStep, StepOutput
from mas.lab.benchmark.pipeline.resolver import DependencyResolver
from mas.lab.benchmark.pipeline.cache import CacheManager
from mas.lab.benchmark.pipeline.resources import (
    ResourceRegistry,
    ScopeContext,
    resolve_resource_refs,
)
from mas.lab.benchmark.pipeline.schema_validation import validate_payload
from mas.lab import paths as _paths


logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Plan for pipeline execution."""
    
    execution_order: List[str]
    """Steps in execution order."""
    
    steps_to_rerun: List[str]
    """Steps that will be rerun (cache miss or force_rerun)."""
    
    steps_cached: List[str]
    """Steps that will be skipped (cache hit)."""
    
    execution_layers: List[List[str]]
    """Layers for parallel execution."""
    
    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Execution Plan:",
            f"  Total steps: {len(self.execution_order)}",
            f"  To rerun: {len(self.steps_to_rerun)} ({', '.join(self.steps_to_rerun) or 'none'})",
            f"  Cached: {len(self.steps_cached)} ({', '.join(self.steps_cached) or 'none'})",
            f"  Layers: {len(self.execution_layers)} (max parallelism: {max(len(l) for l in self.execution_layers) if self.execution_layers else 0})",
        ]
        return "\n".join(lines)


@dataclass
class ExecutionContext:
    """Context passed to step execution."""
    
    pipeline: Pipeline
    """Pipeline being executed."""
    
    output_dir: Path
    """Base output directory."""
    
    cache_manager: CacheManager
    """Cache manager."""
    
    step_outputs: Dict[str, StepOutput] = field(default_factory=dict)
    """Outputs from completed steps."""
    
    dry_run: bool = False
    """If True, don't actually execute steps."""

    template_vars: Dict[str, Any] = field(default_factory=dict)
    """User-supplied template variables (e.g. events_jsonl, run_id, ...).

    Available for ``{key}`` substitution in step config strings.
    ``output_dir`` is always pre-populated from ``ctx.output_dir``.
    """

    progress_sink: Optional[Callable[[str], None]] = None
    """Optional callable receiving JSON-encoded progress events.

    Called by batch steps after each item with a JSON string of the form::

        {"type": "fanout_progress", "step": "...", "total": N, "done": k, ...}

    The SSE server uses this to stream live progress to the UI.
    """

    def emit_progress(self, data: Dict[str, Any]) -> None:
        """Emit a progress event to the registered sink (if any)."""
        if self.progress_sink is not None:
            try:
                self.progress_sink(json.dumps(data))
            except Exception as exc:
                logger.warning("progress_sink failed: %s", exc)

    resource_registry: Optional[ResourceRegistry] = None
    """Scoped resource manager (KG instances, accumulators, etc.)."""

    scope_context: ScopeContext = field(default_factory=ScopeContext)
    """Current position in the experiment hierarchy (for resource resolution)."""

    workspace_data: Optional[Path] = None
    """Workspace-wide data root (for SHARED-scope artifacts).

    Resolved from env var ``MAS_DATA_ROOT``, experiment config ``workspace_data``,
    or :func:`mas.lab.paths.data_root` as the default.  Steps must not hardcode
    paths for shared resources; use
    :class:`~mas.lab.benchmark.pipeline.resources.Artifact` with
    ``scope=Scope.SHARED`` and call ``artifact.resolve_path(ctx)`` instead.
    """

    lab_name: str = ""
    """Name of the lab, used to derive the SHARED-scope subdirectory."""

    lab_data_dir: Optional[Path] = None
    """Directory containing static input datasets bundled with the lab.

    Derived from the lab root's ``data/`` subdirectory when a ``lab-config.yaml``
    file is found in parent directories.  Steps should use this instead of
    relative paths like ``../../data/`` in their config.
    """

    def get_dependency_output(self, step_name: str) -> Dict[str, Any]:
        """Get output data from a dependency step."""
        if step_name not in self.step_outputs:
            raise ValueError(f"Step '{step_name}' has not been executed yet")
        
        return self.step_outputs[step_name].data

    def get_resource(self, name: str) -> Any:
        """Get a scoped resource by name.

        The resource is resolved at its declared scope using the current
        ``scope_context``.  Raises ``KeyError`` if the resource is not
        declared or ``RuntimeError`` if no registry is available.
        """
        if self.resource_registry is None:
            raise RuntimeError(
                f"No resource registry — cannot resolve resource '{name}'. "
                "Declare resources in the experiment pipeline."
            )
        return self.resource_registry.get(name, self.scope_context)

    def resolve_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve ``@resource:xxx`` references in a step config dict.

        Returns the config unchanged if no resource registry is set.
        """
        if self.resource_registry is None:
            return config
        return resolve_resource_refs(config, self.resource_registry, self.scope_context)
    
    def get_step_output_dir(self, step_name: str) -> Path:
        """Get output directory for a step.

        When ``scope_context`` identifies a run, write into the run folder
        (``{output_dir}/{scenario}/{test}/{run}/``) instead of ``data/{step}/``.
        """
        sc = self.scope_context
        if sc.scenario and sc.test and sc.run:
            return self.output_dir / sc.scenario / sc.test / sc.run
        return self.output_dir / "data" / step_name
    
    def get_step_log_dir(self, step_name: str) -> Path:
        """Get log directory for a step."""
        return self.output_dir / "logs" / step_name


@dataclass
class ExecutionResult:
    """Result of pipeline execution."""
    
    success: bool
    """Whether all steps succeeded."""
    
    executed_steps: List[str]
    """Steps that were executed."""
    
    failed_steps: List[str]
    """Steps that failed."""
    
    step_outputs: Dict[str, StepOutput]
    """Outputs from all steps."""
    
    duration_ms: float
    """Total execution time in milliseconds."""
    
    def summary(self) -> str:
        """Human-readable summary."""
        status = "✓ SUCCESS" if self.success else "✗ FAILED"
        lines = [
            f"Execution Result: {status}",
            f"  Executed: {len(self.executed_steps)} steps",
            f"  Failed: {len(self.failed_steps)} steps",
            f"  Duration: {self.duration_ms:.0f}ms ({self.duration_ms/1000:.1f}s)",
        ]
        
        if self.failed_steps:
            lines.append(f"  Failed steps: {', '.join(self.failed_steps)}")
        
        return "\n".join(lines)


def _find_lab_meta(
    config_path: Optional[Path],
    override_name: str = "",
) -> tuple[str, Optional[Path]]:
    """Walk parent directories to find ``lab-config.yaml`` and extract lab metadata.

    Returns ``(lab_name, lab_data_dir)`` where *lab_data_dir* is the
    ``data/`` subdirectory of the lab root, or ``None`` if not found.
    """
    if config_path is None:
        return override_name, None

    candidate = config_path.resolve().parent
    for _ in range(6):  # max 6 levels up
        lab_yaml = candidate / "lab-config.yaml"
        if lab_yaml.exists():
            name = override_name
            if not name and _yaml is not None:
                try:
                    with open(lab_yaml, encoding="utf-8") as fh:
                        data = _yaml.safe_load(fh) or {}
                    name = (data.get("lab") or {}).get("name", "")
                except Exception as exc:
                    logger.debug("Could not read lab name from %s: %s", lab_yaml, exc)
            if not name:
                # Fallback: strip .lab suffix from directory name
                name = candidate.name.removesuffix(".lab")
            data_dir = candidate / "data"
            return name, (data_dir if data_dir.is_dir() else None)
        candidate = candidate.parent

    # Not found — best-effort from directory name
    fallback_name = override_name or config_path.parent.parent.name.removesuffix(".lab")
    return fallback_name, None


class PipelineExecutor:
    """Executes pipelines with dependency resolution and caching."""
    
    def __init__(
        self,
        pipeline: Pipeline,
        output_dir: Optional[Path] = None,
        resource_registry: Optional[ResourceRegistry] = None,
        scope_context: Optional[ScopeContext] = None,
        progress: bool = False,
        workspace_data: Optional[Path] = None,
        lab_name: str = "",
        data_cache_dir: Optional[Path] = None,
    ):
        self.pipeline = pipeline
        self.resource_registry = resource_registry
        self.progress = progress
        self.scope_context = scope_context or ScopeContext()
        # workspace_data: prefer explicit arg, then MAS_DATA_ROOT env var, then default
        if workspace_data is not None:
            self.workspace_data: Optional[Path] = workspace_data
        elif os.environ.get(_paths.MAS_DATA_ROOT_ENV):
            self.workspace_data = Path(os.environ[_paths.MAS_DATA_ROOT_ENV]).expanduser()
        else:
            self.workspace_data = _paths.data_root()

        # Derive lab_name and lab_data_dir by finding lab-config.yaml in parent dirs
        self.lab_name, self.lab_data_dir = _find_lab_meta(
            pipeline.config_path, override_name=lab_name
        )
        
        # Determine output directory
        if output_dir is None:
            base_dir = pipeline.config.output.get("base_dir", "./output")
            expanded = Path(base_dir).expanduser()
            if expanded.is_absolute():
                output_dir = expanded
            else:
                # Relative base_dir always anchors at the canonical lab-output
                # root — never inside the workspace tree, regardless of whether
                # a config_path is available.
                stem = pipeline.config_path.stem if pipeline.config_path else "pipeline"
                output_dir = _paths.lab_output() / stem / Path(base_dir).name
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup cache
        cache_dir = data_cache_dir if data_cache_dir is not None else self.output_dir / ".cache"
        self.cache_manager = CacheManager(cache_dir)
        
        # Setup resolver
        self.resolver = DependencyResolver(pipeline)
    
    async def run(
        self,
        steps: Optional[List[str]] = None,
        force_rerun: Optional[List[str]] = None,
        dry_run: bool = False,
        parallel: bool = False,
        template_vars: Optional[Dict[str, Any]] = None,
        progress_sink: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """Execute pipeline.
        
        Args:
            steps: Specific steps to run (None = all). Dependencies are included automatically.
            force_rerun: Steps to force rerun (ignores cache)
            dry_run: If True, show execution plan without executing
            parallel: If True, execute independent steps in parallel
            
        Returns:
            ExecutionResult with status and outputs
        """
        start_time = datetime.now()
        
        force_rerun = set(force_rerun or [])
        
        # Resolve execution order
        execution_order = self.resolver.resolve(steps)
        
        # Build execution context
        ctx = ExecutionContext(
            pipeline=self.pipeline,
            output_dir=self.output_dir,
            cache_manager=self.cache_manager,
            dry_run=dry_run,
            resource_registry=self.resource_registry,
            scope_context=self.scope_context,
            workspace_data=self.workspace_data,
            lab_name=self.lab_name,
            lab_data_dir=self.lab_data_dir,
            template_vars=dict(template_vars or {}),
            progress_sink=progress_sink,
        )
        
        # Determine which steps need to rerun
        steps_to_rerun = []
        steps_cached = []
        
        for step_name in execution_order:
            step = self.pipeline.get_step(step_name)
            
            # Get dependency outputs
            dep_outputs = {
                dep: ctx.step_outputs[dep]
                for dep in step.depends_on
                if dep in ctx.step_outputs
            }
            
            # Check cache
            should_rerun = (
                step_name in force_rerun
                or self.cache_manager.should_rerun(step, dep_outputs, self.output_dir)
            )
            
            if should_rerun:
                steps_to_rerun.append(step_name)
            else:
                steps_cached.append(step_name)
        
        # Build execution plan
        execution_layers = self.resolver.get_execution_layers(steps)
        
        plan = ExecutionPlan(
            execution_order=execution_order,
            steps_to_rerun=steps_to_rerun,
            steps_cached=steps_cached,
            execution_layers=execution_layers,
        )
        
        # Log plan
        logger.info(plan.summary())
        
        if self.progress:
            n_total = len(execution_order)
            n_run = len(steps_to_rerun)
            n_cached = len(steps_cached)
            print(f"\nPipeline: {n_total} steps ({n_run} to run, {n_cached} cached)")
            if steps_cached:
                print(f"  cached: {', '.join(steps_cached)}")
            if steps_to_rerun:
                print(f"  to run: {', '.join(steps_to_rerun)}")
            print()
        
        if dry_run:
            # Propagate dry_run flag into every step's config so each step
            # performs safe/stdout-only output instead of real I/O.
            for step in self.pipeline.steps:
                step.config["dry_run"] = True
            logger.info("[dry-run] Injected dry_run=True into all %d step configs", len(self.pipeline.steps))
        
        # Execute steps
        executed_steps = []
        failed_steps = []

        # Restore cached steps: iterate the step's declared output_artifacts and
        # load each one from disk.  Steps that produced no serialized artifacts
        # (output_artifacts == []) cannot be resumed and are demoted to rerun.
        for step_name in list(steps_cached):
            step = self.pipeline.get_step(step_name)
            if step is None:
                continue
            artifacts = step.output_artifacts
            if not artifacts:
                logger.info("Step '%s' declares no output_artifacts — will re-run", step_name)
                steps_cached.remove(step_name)
                steps_to_rerun.append(step_name)
                continue
            data: dict = {}
            files: list = []
            failed = False
            for data_key, artifact in artifacts:
                # Prefer a pre-resolved path attached by the step; fall back to
                # ctx-based resolution so the step doesn't need to know output_dir.
                path = getattr(artifact, "_resolved_path", None)
                if path is None:
                    path = artifact.resolve_path(ctx)
                value = artifact.load(path)
                if value is None:
                    logger.info(
                        "Step '%s': artifact '%s' not found at %s — will re-run",
                        step_name, data_key, path,
                    )
                    failed = True
                    break
                data[data_key] = value
                if path.exists():
                    files.append(path)
            if failed:
                steps_cached.remove(step_name)
                steps_to_rerun.append(step_name)
            else:
                from mas.lab.benchmark.pipeline import StepOutput as _SO
                ctx.step_outputs[step_name] = _SO(
                    data=data, files=files, metadata={"cached": True}
                )
                logger.info("Step '%s' restored from %d artifact(s)", step_name, len(artifacts))

        if parallel:
            # Execute by layers (parallel within layer)
            for layer in execution_layers:
                layer_steps = [s for s in layer if s in steps_to_rerun]
                if not layer_steps:
                    continue
                
                # Execute layer in parallel
                tasks = [
                    self._execute_step(step_name, ctx)
                    for step_name in layer_steps
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for step_name, result in zip(layer_steps, results):
                    if isinstance(result, Exception):
                        logger.error(f"Step '{step_name}' failed: {result}")
                        failed_steps.append(step_name)
                    else:
                        executed_steps.append(step_name)
        else:
            # Sequential execution — continue past independent failures
            for step_name in execution_order:
                if step_name not in steps_to_rerun:
                    continue
                
                # Skip only if a direct dependency already failed
                _step = self.pipeline.get_step(step_name)
                _dep_failed = _step is not None and any(
                    dep in failed_steps for dep in (_step.depends_on or [])
                )
                if _dep_failed:
                    _failed_deps = [d for d in _step.depends_on if d in failed_steps]
                    logger.warning(
                        "Skipping '%s': dependency failed (%s)",
                        step_name, _failed_deps,
                    )
                    failed_steps.append(step_name)
                    continue
                
                try:
                    await self._execute_step(step_name, ctx)
                    executed_steps.append(step_name)
                except Exception as e:
                    # Fatal errors (missing API key, authentication failure) must
                    # propagate immediately rather than being recorded as a soft
                    # step failure.
                    _err = str(e)
                    if (
                        "AuthenticationError" in type(e).__name__
                        or "Incorrect API key" in _err
                        or "invalid_api_key" in _err
                        or "is not set" in _err
                        or ("401" in _err and "api" in _err.lower())
                    ):
                        raise
                    logger.error(f"Step '{step_name}' failed: {e}")
                    failed_steps.append(step_name)
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        result = ExecutionResult(
            success=len(failed_steps) == 0,
            executed_steps=executed_steps,
            failed_steps=failed_steps,
            step_outputs=ctx.step_outputs,
            duration_ms=duration_ms,
        )
        
        logger.info(result.summary())
        
        return result
    
    async def _execute_step(
        self,
        step_name: str,
        ctx: ExecutionContext,
    ):
        """Execute a single step."""
        step = self.pipeline.get_step(step_name)
        logger.info(f"Executing step: {step_name} (type: {step.type})")
        
        if self.progress:
            print(f"  ▶ {step_name} ({step.type}) ...", end="", flush=True)
        
        step_start = datetime.now()
        
        # Resolve @resource:xxx references in step config before execution
        if ctx.resource_registry is not None:
            step.config = ctx.resolve_config(step.config)
        # Resolve {output_dir} and user template_vars in step config
        step.config = self._resolve_config_templates(step.config, ctx)

        # Align scope context with per-run step config so Artifact.resolve_path works.
        cfg = step.config or {}
        if cfg.get("scenario") or cfg.get("test") or cfg.get("run"):
            ctx.scope_context = ScopeContext(
                experiment=ctx.scope_context.experiment,
                scenario=str(cfg.get("scenario", "")),
                test=str(cfg.get("test", "")),
                run=str(cfg.get("run", "")),
            )

        schema_base_dir = self.pipeline.config_path.parent if self.pipeline.config_path else Path.cwd()
        input_stream = {
            dep: ctx.step_outputs[dep].data
            for dep in step.depends_on
            if dep in ctx.step_outputs
        }
        from mas.lab.benchmark.pipeline.run_artifacts import run_input_stream

        run_payload = run_input_stream(ctx, step.config)
        if run_payload:
            input_stream["_run"] = run_payload
            step.config.setdefault("run_dir", run_payload.get("run_dir", ""))
            for key in ("scenario", "test", "run", "events_path", "trace_path"):
                if run_payload.get(key) and not step.config.get(key):
                    step.config[key] = run_payload[key]
        validate_payload(
            input_stream,
            step.config.get("input_schema"),
            label=f"Step '{step_name}' input stream",
            base_dir=schema_base_dir,
        )

        # Execute
        output = await step.execute(ctx)

        validate_payload(
            output.data,
            step.config.get("output_schema"),
            label=f"Step '{step_name}' output data",
            base_dir=schema_base_dir,
        )
        
        step_duration = (datetime.now() - step_start).total_seconds() * 1000
        output.metadata["duration_ms"] = step_duration
        
        # Store output
        ctx.step_outputs[step_name] = output
        
        # Update cache
        dep_outputs = {
            dep: ctx.step_outputs[dep]
            for dep in step.depends_on
            if dep in ctx.step_outputs
        }
        fingerprint = self.cache_manager.compute_fingerprint(step, dep_outputs)
        self.cache_manager.save_fingerprint(step_name, fingerprint)
        
        if self.progress:
            _data_summary = ""
            if "rows" in output.data:
                _data_summary = f" [{output.data['rows']} rows]"
            elif "metrics_computed" in output.data:
                _mc = output.data["metrics_computed"]
                _cc = output.data.get("metrics_cached", 0)
                _data_summary = f" [computed={_mc}, cached={_cc}]"
            print(f" ✓ {step_duration:.0f}ms{_data_summary}")
        
        logger.info(f"✓ Step '{step_name}' completed in {step_duration:.0f}ms")

    @staticmethod
    def _resolve_config_templates(
        config: Dict[str, Any],
        ctx: "ExecutionContext",
    ) -> Dict[str, Any]:
        """Substitute ``{key}`` placeholders in string config values.

        The substitution namespace is built from (in priority order):
        1. ``ctx.template_vars`` — user-supplied variables
        2. ``output_dir`` from ``ctx.output_dir``
        3. ``os.environ`` — environment variables

        Non-string values are returned unchanged.  Missing keys are left as-is
        so that steps can carry ``{key}`` literals through without erroring.
        """
        namespace: Dict[str, str] = {}
        # Lowest priority: env
        for k, v in os.environ.items():
            namespace[k] = v
        # Mid priority: output_dir
        namespace["output_dir"] = str(ctx.output_dir)
        # High priority: user-supplied template vars
        for k, v in ctx.template_vars.items():
            namespace[k] = str(v)

        def _substitute(value: Any) -> Any:
            if isinstance(value, str):
                return re.sub(
                    r"\{([^}]+)\}",
                    lambda m: namespace.get(m.group(1), m.group(0)),
                    value,
                )
            if isinstance(value, dict):
                return {k: _substitute(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_substitute(item) for item in value]
            return value

        return _substitute(config)  # type: ignore[return-value]

    def plan(
        self,
        steps: Optional[List[str]] = None,
        force_rerun: Optional[List[str]] = None,
    ) -> ExecutionPlan:
        """Get execution plan without running.
        
        Useful for:
        - Previewing what will run
        - Understanding dependencies
        - Debugging pipeline structure
        """
        # Build plan directly (avoid async issues)
        execution_order = self.resolver.resolve(steps)
        execution_layers = self.resolver.get_execution_layers(steps)
        
        force_rerun_set = set(force_rerun or [])
        steps_to_rerun = []
        steps_cached = []
        
        for step_name in execution_order:
            if step_name in force_rerun_set:
                steps_to_rerun.append(step_name)
            else:
                # Check cache (without dependency outputs, conservative)
                cached_fp = self.cache_manager.get_cached_fingerprint(step_name)
                if cached_fp is None:
                    steps_to_rerun.append(step_name)
                else:
                    steps_cached.append(step_name)
        
        return ExecutionPlan(
            execution_order=execution_order,
            steps_to_rerun=steps_to_rerun,
            steps_cached=steps_cached,
            execution_layers=execution_layers,
        )
