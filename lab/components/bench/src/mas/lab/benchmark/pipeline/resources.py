#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
"""
Scoped resource management for pipeline execution.

Resources (KG instances, shared state, accumulators) are declared at any
level of the experiment hierarchy and available to steps executing at that
level or any narrower (lower) scope.

Scope hierarchy (widest → narrowest):

    experiment → scenario → test → run

A KG declared at ``test`` scope persists across all runs within that test.
A normalization step at ``run`` scope can read that KG as a parameter.

Resources can be declared at **experiment level** or **scenario level** in
the experiment YAML.  Scenario-level resources override experiment-level
ones with the same name:

Usage in experiment YAML::

    # Experiment-level resources — visible to all scenarios
    pipeline_resources:
      - name: shared-kg
        type: kg
        scope: test

    scenarios:
      - id: baseline
        # Scenario-level resources — visible only within this scenario
        pipeline_resources:
          - name: scenario-kg
            type: kg
            scope: scenario

      steps:
        - name: normalize
          type: normalize_events
          scope: run
          config:
            kg: "@resource:shared-kg"   # reference to test-scoped KG

Steps reference resources via ``@resource:<name>`` in their config values.
The executor resolves these references before calling ``step.execute()``.
"""


import logging
from abc import abstractmethod
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from mas.lab.benchmark.pipeline.schema_validation import validate_payload

logger = logging.getLogger(__name__)


class Scope(IntEnum):
    """Pipeline scope levels, ordered widest → narrowest.

    Integer ordering means ``Scope.SHARED < Scope.RUN`` — a wider scope
    has a smaller value.  A resource declared at scope S is visible to any
    step whose execution scope is ≥ S.

    ``SHARED`` is special: it lives outside any single experiment run,
    in a workspace-wide data directory (e.g. ``<data_root>/<lab>/shared/`` via
    :func:`mas.lab.paths.data_root`).
    Use it for pre-built indexes, ingested corpora, or any resource whose
    construction cost should not be repeated per experiment.
    """

    SHARED = -1
    EXPERIMENT = 0
    SCENARIO = 1
    TEST = 2
    RUN = 3

    @classmethod
    def from_str(cls, s: str) -> "Scope":
        return cls[s.upper()]


# ---------------------------------------------------------------------------
# Artifact — a named file produced or consumed by a pipeline step
# ---------------------------------------------------------------------------

#: Canonical file extensions for artifact formats.
_FORMAT_EXT: Dict[str, str] = {
    "json": "json",
    "csv": "csv",
    "sqlite": "db",
    "session_store": "",   # directory, no extension
    "png": "png",
    "svg": "svg",
    "parquet": "parquet",
    "txt": "txt",
}


@dataclass
class Artifact:
    """A named file (or directory) produced or consumed by a pipeline step.

    The artifact's path on disk is fully derived from its name, format, and
    scope — no hardcoded paths anywhere.  Given an :class:`ExecutionContext`,
    call :meth:`resolve_path` to get the concrete filesystem path.

    Path derivation::

        SHARED      → <workspace_data>/<lab>/shared/<name>.<ext>
        EXPERIMENT  → <output_dir>/<name>.<ext>
        SCENARIO    → <output_dir>/<scenario>/<name>.<ext>
        TEST        → <output_dir>/<scenario>/<test>/<name>.<ext>
        RUN         → <output_dir>/<scenario>/<test>/<run>/<name>.<ext>

    The hierarchy is nested: a test lives inside its scenario, a run lives
    inside its test.  This mirrors the benchmark output directory layout
    ``<output_dir>/<scenario>/item<id>/r<N>/`` where ``test = item<id>``
    and ``run = r<N>``.

    Artifacts with ``format="session_store"`` are directories (no extension).
    """

    name: str
    """Logical name of the artifact (used as filename stem)."""

    format: str
    """Serialization format: ``json``, ``csv``, ``sqlite``, ``session_store``, …"""

    scope: Scope = Scope.EXPERIMENT
    """Scope that determines the base directory."""

    schema: Optional[Any] = None
    """Optional JSON Schema (dict or file path) used to validate payloads.

    When set, ``dump()`` validates outgoing data before writing and ``load()``
    validates loaded data before returning it.
    """

    def resolve_path(self, ctx: Any) -> Path:  # ctx: ExecutionContext
        """Return the concrete path for this artifact given *ctx*.

        ``ctx`` must have:
        - ``output_dir: Path``
        - ``scope_context: ScopeContext``
        - ``workspace_data: Optional[Path]`` (for SHARED scope)
        - ``lab_name: str`` (for SHARED scope)
        """
        ext = _FORMAT_EXT.get(self.format, self.format)
        filename = self.name if not ext else f"{self.name}.{ext}"

        if self.scope == Scope.SHARED:
            workspace_data: Optional[Path] = getattr(ctx, "workspace_data", None)
            lab_name: str = getattr(ctx, "lab_name", "")
            if workspace_data is None:
                raise RuntimeError(
                    f"Artifact '{self.name}' is SHARED but ctx.workspace_data is not set. "
                    "Set MAS_DATA env var or workspace_data in the experiment config."
                )
            base = workspace_data / lab_name / "shared"
        elif self.scope == Scope.EXPERIMENT:
            base = ctx.output_dir
        elif self.scope == Scope.SCENARIO:
            base = ctx.output_dir / ctx.scope_context.scenario
        elif self.scope == Scope.TEST:
            base = ctx.output_dir / ctx.scope_context.scenario / ctx.scope_context.test
        else:  # RUN
            base = ctx.output_dir / ctx.scope_context.scenario / ctx.scope_context.test / ctx.scope_context.run

        # session_store is a directory — return the directory path itself
        if self.format == "session_store":
            return base / self.name
        return base / filename

    def exists(self, ctx: Any) -> bool:
        """True if the artifact already exists on disk."""
        return self.resolve_path(ctx).exists()

    def load(self, path: Path) -> Any:
        """Deserialize the artifact from *path*.

        Supported formats: ``json``, ``jsonl``, ``csv``.  Returns ``None``
        when the file does not exist or the format is not recognized.
        """
        if not path.exists():
            return None
        fmt = self.format
        value: Any = None
        try:
            if fmt == "json":
                import json as _json
                value = _json.loads(path.read_text(encoding="utf-8"))
            elif fmt == "jsonl":
                import json as _json
                value = [
                    _json.loads(ln)
                    for ln in path.read_text(encoding="utf-8").splitlines()
                    if ln.strip()
                ]
            elif fmt == "csv":
                import csv as _csv
                with open(path, newline="", encoding="utf-8") as f:
                    value = list(_csv.DictReader(f))
            else:
                return None

            if self.schema is not None:
                validate_payload(
                    value,
                    self.schema,
                    label=f"Artifact '{self.name}' loaded from {path}",
                    base_dir=path.parent,
                )
            return value
        except Exception:
            logger.exception("Artifact.load failed for %s (format=%s)", path, fmt)
        return None

    def dump(self, value: Any, path: Path) -> None:
        """Serialize *value* to *path* according to :attr:`format`.

        Supported formats: ``json``, ``jsonl``, ``csv`` (list-of-dicts only).
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.schema is not None:
            validate_payload(
                value,
                self.schema,
                label=f"Artifact '{self.name}' write to {path}",
                base_dir=path.parent,
            )
        fmt = self.format
        if fmt == "json":
            import json as _json
            path.write_text(_json.dumps(value, indent=2), encoding="utf-8")
        elif fmt == "jsonl":
            import json as _json
            path.write_text(
                "\n".join(_json.dumps(item) for item in value), encoding="utf-8"
            )
        elif fmt == "csv":
            import csv as _csv
            if not value:
                path.write_text("", encoding="utf-8")
                return
            fieldnames = list(value[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(value)
        else:
            raise ValueError(f"Artifact.dump: unsupported format '{fmt}'")


class Resource(Artifact):
    """An :class:`Artifact` that is long-lived, appendable, and resumable.

    Resources differ from plain artifacts in two ways:

    1. They default to ``Scope.SHARED`` — their contents should survive
       across experiment runs so they are not rebuilt unnecessarily.
    2. They support explicit :meth:`serialize` / :meth:`deserialize` so
       the pipeline can resume an interrupted build instead of restarting.

    Subclass and implement :meth:`serialize` / :meth:`deserialize` for
    concrete resource types (SQLite observation store, session store, …).
    """

    scope: Scope = Scope.SHARED

    @abstractmethod
    def serialize(self, path: Path) -> None:
        """Persist current state to *path*."""

    @abstractmethod
    def deserialize(self, path: Path) -> None:
        """Restore state from *path*."""

    def resume_or_build(self, ctx: Any, *, force: bool = False) -> bool:
        """Try to restore from disk; return True if loaded, False if build needed.

        When ``force=True`` skips the disk check and signals a fresh build.
        """
        if force:
            return False
        path = self.resolve_path(ctx)
        if path.exists():
            self.deserialize(path)
            return True
        return False


@dataclass
class ResourceSpec:
    """Declarative specification of a scoped pipeline resource."""

    name: str
    """Unique resource name within the pipeline."""

    type: str
    """Resource type key (e.g. ``kg``, ``accumulator``, ``dataframe``)."""

    scope: Scope
    """Scope at which this resource lives."""

    config: Dict[str, Any] = field(default_factory=dict)
    """Type-specific configuration."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceSpec":
        return cls(
            name=data["name"],
            type=data["type"],
            scope=Scope.from_str(data.get("scope", "run")),
            config=data.get("config", {}),
        )


# ---------------------------------------------------------------------------
# Resource factories
# ---------------------------------------------------------------------------

_FACTORIES: dict[str, Any] = {}


def create_resource(spec: ResourceSpec) -> Any:
    """Instantiate a resource from its spec."""
    factory = _FACTORIES.get(spec.type)
    if factory is None:
        raise ValueError(
            f"Unknown resource type '{spec.type}' for resource '{spec.name}'. "
            f"Available: {sorted(_FACTORIES)}"
        )
    return factory(spec)


# ---------------------------------------------------------------------------
# ScopeContext — identifies the current execution position in the hierarchy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScopeContext:
    """Identifies the current position in the experiment hierarchy.

    Used as a compound key for resource lifecycle management.
    """

    experiment: str = ""
    scenario: str = ""
    test: str = ""
    run: str = ""

    def at_scope(self, scope: Scope) -> "ScopeContext":
        """Return a copy truncated to the given scope (zeroing narrower fields).

        This gives a stable key for resource lookup at wider scopes.
        E.g., ``ctx.at_scope(Scope.TEST)`` keeps experiment+scenario+test
        but drops run — so all runs within the same test share the key.
        """
        fields = {}
        if scope >= Scope.EXPERIMENT:
            fields["experiment"] = self.experiment
        if scope >= Scope.SCENARIO:
            fields["scenario"] = self.scenario
        if scope >= Scope.TEST:
            fields["test"] = self.test
        if scope >= Scope.RUN:
            fields["run"] = self.run
        return ScopeContext(**fields)

    def scope_key(self, scope: Scope) -> str:
        """Flat string key for a resource at the given scope."""
        ctx = self.at_scope(scope)
        parts = [ctx.experiment, ctx.scenario, ctx.test, ctx.run]
        return "/".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# ResourceRegistry — lifecycle manager for scoped resources
# ---------------------------------------------------------------------------

class ResourceRegistry:
    """Manages scoped resource instances across the experiment hierarchy.

    Resources are lazily instantiated on first access and keyed by
    ``(resource_name, scope_key)`` so narrower-scope resources get fresh
    instances while wider-scope resources are shared.

    Typical lifecycle::

        registry = ResourceRegistry(specs)

        # At the start of each run:
        registry.enter_scope(scope_ctx)

        # Steps resolve @resource:xxx references:
        kg = registry.get("shared-kg", scope_ctx)

        # At the end of a scope (e.g., test boundary):
        registry.exit_scope(Scope.TEST, scope_ctx)  # resets run-level resources
    """

    def __init__(self, specs: List[ResourceSpec]) -> None:
        self._specs: Dict[str, ResourceSpec] = {s.name: s for s in specs}
        # (resource_name, scope_key) → live instance
        self._instances: Dict[tuple, Any] = {}

    @property
    def specs(self) -> Dict[str, ResourceSpec]:
        return self._specs

    def get(self, name: str, scope_ctx: ScopeContext) -> Any:
        """Get (or lazily create) a resource instance.

        The resource is looked up at its declared scope, using scope_ctx
        to derive the appropriate key.  All runs within the same test
        get the same test-scoped resource instance.
        """
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"Unknown resource '{name}'. Declared: {sorted(self._specs)}")

        key = (name, scope_ctx.scope_key(spec.scope))
        if key not in self._instances:
            logger.debug("Creating resource '%s' at scope %s (key=%s)", name, spec.scope.name, key[1])
            self._instances[key] = create_resource(spec)
        return self._instances[key]

    def reset_scope(self, scope: Scope, scope_ctx: ScopeContext) -> None:
        """Reset (destroy) all resources at exactly the given scope.

        Called at scope boundaries — e.g., when transitioning from one test
        to another, resources at ``Scope.RUN`` are reset.

        Resources at *wider* scopes (smaller enum value) are preserved.
        """
        to_remove = []
        for (rname, skey), inst in self._instances.items():
            spec = self._specs.get(rname)
            if spec and spec.scope == scope and skey == scope_ctx.scope_key(scope):
                to_remove.append((rname, skey))
        for k in to_remove:
            inst = self._instances.pop(k)
            # Call cleanup if available
            if hasattr(inst, "reset"):
                inst.reset()
            elif hasattr(inst, "close"):
                inst.close()
            logger.debug("Reset resource '%s' at scope %s", k[0], scope.name)

    def reset_narrower_than(self, scope: Scope, scope_ctx: ScopeContext) -> None:
        """Reset all resources at scopes narrower than (>) the given scope.

        E.g., ``reset_narrower_than(Scope.TEST, ctx)`` resets all RUN-scoped
        resources while preserving TEST, SCENARIO, and EXPERIMENT resources.
        """
        for s in Scope:
            if s > scope:
                self.reset_scope(s, scope_ctx)

    def reset_all(self) -> None:
        """Reset all resources (end of experiment)."""
        for (rname, skey), inst in list(self._instances.items()):
            if hasattr(inst, "reset"):
                inst.reset()
            elif hasattr(inst, "close"):
                inst.close()
        self._instances.clear()


# ---------------------------------------------------------------------------
# Config resolution — replace @resource:xxx references
# ---------------------------------------------------------------------------

RESOURCE_PREFIX = "@resource:"


def resolve_resource_refs(
    config: Any,
    registry: ResourceRegistry,
    scope_ctx: ScopeContext,
) -> Any:
    """Recursively resolve ``@resource:<name>`` strings in a config tree.

    Returns a new config tree with resource references replaced by live
    resource instances.  Non-string values and strings without the prefix
    are passed through unchanged.
    """
    if isinstance(config, str) and config.startswith(RESOURCE_PREFIX):
        name = config[len(RESOURCE_PREFIX):]
        return registry.get(name, scope_ctx)
    if isinstance(config, dict):
        return {k: resolve_resource_refs(v, registry, scope_ctx) for k, v in config.items()}
    if isinstance(config, list):
        return [resolve_resource_refs(v, registry, scope_ctx) for v in config]
    return config
