#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from mas.runtime.spec.source import resolve_path as resolve_path_ref

@dataclass
class OverlayStack:
    """Layered overlay stacks — logic, control, infra applied in that order."""

    logic: "List[Union[str, dict]]" = field(default_factory=list)
    control: "List[Union[str, dict]]" = field(default_factory=list)
    infra: "List[Union[str, dict]]" = field(default_factory=list)

    def flattened(self) -> "List[Union[str, dict]]":
        return list(self.logic) + list(self.control) + list(self.infra)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, scenario_id: str) -> "OverlayStack":
        if not isinstance(data, dict):
            raise ValueError(f"scenario {scenario_id}: overlays must be {{logic, control, infra}}")
        logic = list(data.get("logic") or [])
        control = list(data.get("control") or [])
        infra = list(data.get("infra") or [])
        if not logic and not control and not infra:
            logic = [scenario_id]
        return cls(logic=logic, control=control, infra=infra)


@dataclass
class MASScenarioSpec:
    """One selectable scenario — shared by LabConfig and MASExperimentConfig.

    Parallel to a *variant* in ExperimentConfig: it names one execution
    context for the MAS, optionally overlaying extra configuration on top of
    the base JSON config.
    """

    id: str
    """Scenario ID shown in reports and used as run directory name."""

    description: str = ""
    """Human-readable label shown in the UI dropdown or benchmark report."""

    version: Optional[int] = None
    """Scenario version — tracks overlay iteration history.

    When set, the output directory for this scenario is named
    ``{id}.v{version}`` instead of plain ``{id}``, so that runs from
    different overlay iterations coexist under the same experiment and can be
    compared directly.

    Declare this in the experiment YAML when an overlay has been deliberately
    revised (e.g.  after a new suppression technique is found)::

        scenarios:
          - id: c7-missing-evidence
            version: 2
            description: "Revised — stronger suppression via explicit negative"
          - id: baseline

    Omit ``version`` (or set ``version: 1``) for the first iteration of a
    scenario; increment it whenever the overlay definition changes in a way
    that would invalidate comparison with previous runs.
    """

    overlays: OverlayStack = field(default_factory=OverlayStack)
    """Layered overlay stacks applied logic → control → infra on mas.yaml."""

    inputs: Dict[str, Any] = field(default_factory=dict)
    """Optional scenario-level default inputs (merged into RunInput)."""

    expectations: Dict[str, Any] = field(default_factory=dict)
    """Optional scenario-level expectations (merged into RunInput)."""

    tags: List[str] = field(default_factory=list)
    """Optional labels for grouping / filtering (e.g. ["challenge", "hard"])."""

    user_prompt: str = ""
    """Optional default prompt pre-filled in the topbar when this scenario is selected."""

    flavour: Optional[str] = None
    """Optional per-scenario flavour override.

    When set, this scenario uses the named flavour file instead of the
    experiment-level ``default_flavour``.  Resolved from the same
    search paths (experiment-local ``flavours/``, workspace root, bundled).
    """

    pipeline_resources: List[Dict[str, Any]] = field(default_factory=list)
    """Scoped resource declarations local to this scenario.

    Resources declared here are visible only to pipeline steps executing
    within this scenario (or narrower scopes).  They are merged with
    experiment-level ``pipeline_resources`` at execution time; a
    scenario-level resource with the same name overrides the
    experiment-level one.
    """

    @property
    def output_dir_name(self) -> str:
        """Return the directory name to use for this scenario's outputs.

        Returns ``{id}.v{version}`` when *version* is set, plain ``{id}``
        otherwise (backward-compatible for unversioned scenarios).
        """
        if self.version is not None:
            return f"{self.id}.v{self.version}"
        return self.id

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Path) -> "MASScenarioSpec":
        raw_overlays = data.get("overlays")
        if raw_overlays is None:
            overlay_stack = OverlayStack(logic=[data["id"]])
        else:
            overlay_stack = OverlayStack.from_dict(raw_overlays, scenario_id=data["id"])
        raw_version = data.get("version")
        version: Optional[int] = int(raw_version) if raw_version is not None else None
        return cls(
            id=data["id"],
            description=data.get("description", ""),
            version=version,
            overlays=overlay_stack,
            inputs=dict(data.get("inputs") or {}),
            expectations=dict(data.get("expectations") or {}),
            flavour=data.get("flavour"),
            tags=data.get("tags", []),
            user_prompt=data.get("user_prompt", ""),
            pipeline_resources=data.get("pipeline_resources", []),
        )


@dataclass
class MASSpec:
    """Pointer to a MAS use-case (parallel to AgentSpec for single agents).

    A MAS use-case is a directory holding named scenario files.  Supports two
    resolution strategies:

    * **manifest** (preferred):  ``manifest: path/to/mas.yaml`` — overlays are
      loaded from ``<manifest_parent>/overlays/``.  Preferred for unified
      ``experiment.yaml`` files where scenarios declare
      ``overlays: [list]``.
    * **configs_dir**:  ``configs_dir: path/to/overlays/`` — directory of
      scenario overlay YAML files applied on top of the sibling ``mas.yaml``.
    """

    configs_dir: Optional[Path] = None
    """Absolute path to the scenario overlay directory (typically ``overlays/``)."""

    manifest: Optional[Path] = None
    """Absolute path to the MAS ``mas.yaml`` manifest.

    When set, ``configs_dir`` defaults to ``manifest.parent / "overlays"``
    for auto-discovery and backward-compat helpers.
    """

    base_scenario: str = "baseline"
    """Default scenario to load on startup."""

    @property
    def effective_configs_dir(self) -> Optional[Path]:
        """Return configs_dir or derive it from the manifest parent."""
        if self.configs_dir:
            return self.configs_dir
        if self.manifest:
            return self.manifest.parent / "overlays"
        return None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_dir: Path) -> "MASSpec":
        # ── app: <name>  (preferred — resolves from mas.apps registry) ──────
        if "app" in data:
            from mas.apps import get_app, resolve_app_manifest

            app_root = get_app(data["app"])
            manifest = resolve_app_manifest(app_root, app_id=str(data["app"]))
            configs_dir: Optional[Path] = None
            if "configs_dir" in data:
                configs_dir = resolve_path_ref(str(data["configs_dir"]), base_dir)
            return cls(
                manifest=manifest,
                configs_dir=configs_dir,
                base_scenario=data.get("base_scenario", "baseline"),
            )
        # ── manifest: path/to/mas.yaml  (explicit path) ──────────────────────
        if "manifest" in data:
            manifest = resolve_path_ref(str(data["manifest"]), base_dir)
            configs_dir = None
            if "configs_dir" in data:
                configs_dir = resolve_path_ref(str(data["configs_dir"]), base_dir)
            return cls(
                manifest=manifest,
                configs_dir=configs_dir,
                base_scenario=data.get("base_scenario", "baseline"),
            )
        # ── configs_dir: path/  (legacy) ─────────────────────────────────────
        if "configs_dir" not in data:
            raise ValueError(
                "MASSpec requires one of: 'app', 'manifest', or 'configs_dir'. "
                f"Got keys: {list(data.keys())}"
            )
        configs_dir = resolve_path_ref(str(data["configs_dir"]), base_dir)
        return cls(
            configs_dir=configs_dir,
            base_scenario=data.get("base_scenario", "baseline"),
        )

