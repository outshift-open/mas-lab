#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MAS specification validation module.

Validates MAS manifests (mas.json) for completeness, correctness, and consistency.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Validation error details."""
    severity: str  # "error", "warning", "info"
    category: str  # "structure", "reference", "ontology", "agent", "tool"
    message: str
    path: Optional[str] = None  # JSON path where error occurred
    
    def __str__(self) -> str:
        prefix = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(self.severity, "•")
        location = f" [{self.path}]" if self.path else ""
        return f"{prefix} {self.category.upper()}: {self.message}{location}"


@dataclass
class ValidationResult:
    """Result of MAS specification validation."""
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    info: List[ValidationError]
    
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    def summary(self) -> str:
        """Generate summary string."""
        if self.valid:
            msg = "✅ Validation passed"
            if self.warnings:
                msg += f" ({len(self.warnings)} warnings)"
            return msg
        else:
            return f"❌ Validation failed ({len(self.errors)} errors, {len(self.warnings)} warnings)"


class MASSpecValidator:
    """Validator for MAS manifest specifications."""

    # Maps (api_version, kind) to the JSON Schema YAML filename found in
    # mas.ctl.validate.schemas.  These schemas are the single source of
    # truth for structural / type / required-field validation.  Python checks
    # below add *semantic* constraints that JSON Schema cannot express.
    _SCHEMA_REGISTRY: Dict[Tuple[str, str], str] = {
        # Agent manifests use apiVersion: mas/v1 (not agent/v1)
        ("mas/v1",      "Agent"):        "agent.schema.yaml",
        ("mas/v1",      "MAS"):          "mas.schema.yaml",
        # Overlay
        ("mas/v1",      "Overlay"):      "overlay.schema.yaml",
        ("mas/v1",      "Workflow"):     "workflow.schema.yaml",
        ("workflow/v1", "Workflow"):     "workflow.schema.yaml",
        # Flavour — mas/v1 canonical; flavour/v1 accepted alias (same schema)
        ("mas/v1",      "Flavour"):      "flavour.schema.yaml",
        ("flavour/v1",  "Flavour"):      "flavour.schema.yaml",
        # Tool family
        ("mas/v1",      "Tool"):         "tool.schema.yaml",
        ("mas/v1",      "ToolBundle"):   "tool_bundle.schema.yaml",
        ("mas/v1",      "PromptBundle"): "prompt_bundle.schema.yaml",
    }

    def __init__(self, spec_path: Path, base_dir: Optional[Path] = None,
                 strict: bool = True):
        """Initialize validator.

        Args:
            spec_path: Path to mas.json, mas.yaml, or an overlay YAML.
            base_dir: Base directory for resolving relative file references
                      (defaults to the application root directory).
            strict: When True (default), warn on missing *recommended* fields
                    (spec.role.description, spec.design_pattern,
                    metadata.description).  Use --no-strict to suppress.
        """
        self.spec_path = Path(spec_path)
        self.strict = strict
        self.spec: Optional[Dict] = None
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
        self.info: List[ValidationError] = []
        # base_dir defaults to _app_root, resolved after spec_path is set.
        self._base_dir_override = Path(base_dir) if base_dir else None

    @property
    def base_dir(self) -> Path:
        """Base directory for resolving relative file references."""
        return self._base_dir_override or self._app_root

    @property
    def _app_root(self) -> Path:
        """Root directory of the MAS application (contains mas.yaml).

        When the entry point is an overlay (lives inside an ``overlays/``
        sub-directory), the application root is the *parent* of that
        sub-directory.  In all other cases it is ``spec_path.parent``.
        """
        p = self.spec_path.resolve()
        if p.parent.name == "overlays":
            return p.parent.parent
        return p.parent

    def validate(self) -> ValidationResult:
        """Run full validation suite.

        Pass order:
          1. Load the manifest (YAML or JSON).
          2. JSON Schema validation — every source YAML file against its
             registered schema (single source of truth).
          3. Semantic checks — things JSON Schema cannot express:
             cross-references (entry_agent in agents list), duplicate IDs,
             missing file refs, ontology info.
          4. Strict-mode recommended-field warnings (role.description, etc.)
             are emitted during step 2, on the source YAML, not on _raw.
          5. Manifest separation rules (model/access isolation).

        Returns:
            ValidationResult with categorised issues.
        """
        self.errors = []
        self.warnings = []
        self.info = []

        # 1. Load
        if not self._load_spec():
            return ValidationResult(False, self.errors, self.warnings, self.info)

        # 2. JSON Schema validation (source YAML files)
        self._validate_schemas()

        # 3. Semantic checks
        self._validate_structure()       # cross-references only
        self._check_file_references()    # artifact paths exist
        self._validate_agents()          # duplicate IDs only
        self._check_ontologies()         # informational

        # 4. Manifest separation (model/access isolation)
        self._validate_manifest_separation()

        valid = len(self.errors) == 0
        return ValidationResult(valid, self.errors, self.warnings, self.info)

    # ------------------------------------------------------------------
    # Schema validation (single source of truth)
    # ------------------------------------------------------------------

    def _load_schema(self, api_version: str, kind: str) -> Optional[Dict]:
        """Load the JSON Schema for the given (api_version, kind) pair.

        Schemas live in the ``mas.ctl.validate.schemas`` package directory.
        Returns *None* when no schema is registered (silently skipped).
        """
        import mas.ctl.validate.schemas as _schema_pkg
        from mas.runtime.spec.source import load_yaml_file

        filename = self._SCHEMA_REGISTRY.get((api_version, kind))
        if filename is None:
            return None
        try:
            schema_dir = Path(_schema_pkg.__file__).parent
            return load_yaml_file(schema_dir / filename)
        except Exception:
            return None

    def _validate_schemas(self) -> None:
        """Validate every source YAML file against its registered JSON Schema.

        File discovery is rooted at ``_app_root`` so that both ``mas.yaml``
        and ``overlays/X.yaml`` entry points produce the same coverage.
        When the entry point is itself an overlay, that file is validated
        directly as well (it would not appear in the root glob).
        """
        from mas.runtime.spec.source import load_yaml_file

        root = self._app_root
        candidate_paths: List[Path] = [
            *sorted(root.glob("mas.yaml")),
            *sorted(root.rglob("agents/**/agent.yaml")),
            *sorted(root.glob("overlays/*.yaml")),
            *sorted(root.glob("workflows/*.yaml")),
            *sorted(root.glob("flavours/*.yaml")),
            *sorted(root.glob("tools/*.yaml")),
            *sorted(root.glob("tool_bundles/*.yaml")),
            *sorted(root.glob("prompt_bundles/*.yaml")),
        ]

        # Supplement glob discovery with agent files explicitly referenced in the
        # entry-point YAML (covers non-standard directory names like agents-best/).
        try:
            _raw_spec = load_yaml_file(Path(self.spec_path))
            for _a in _raw_spec.get("spec", {}).get("agents", []):
                _ref = _a.get("ref")
                if _ref:
                    _ref_path = (root / _ref).resolve()
                    if _ref_path.exists():
                        candidate_paths.append(_ref_path)
        except Exception:
            logger.debug("Could not pre-load agent refs from entry spec", exc_info=True)

        # Also validate the entry-point file itself if it is not already covered
        # (e.g. an overlay opened directly from a non-standard path, or mas-best.yaml).
        spec_resolved = self.spec_path.resolve()
        if spec_resolved not in {p.resolve() for p in candidate_paths}:
            candidate_paths.insert(0, self.spec_path)

        # Deduplicate while preserving order (glob + ref discovery may overlap).
        _seen: set = set()
        unique_paths: List[Path] = []
        for _p in candidate_paths:
            _key = _p.resolve()
            if _key not in _seen:
                _seen.add(_key)
                unique_paths.append(_p)
        candidate_paths = unique_paths

        for yaml_path in candidate_paths:
            self._validate_single_schema(yaml_path)

    def _validate_single_schema(self, yaml_path: Path) -> None:
        """Validate one YAML file via mas.ctl.validate (schema + separation + refs)."""
        from mas.ctl.validate.schemas import declared_kind, schema_path_for_kind
        from mas.ctl.validate.validator import validate_data
        from mas.runtime.spec.source import load_yaml_file

        try:
            data = load_yaml_file(yaml_path)
        except Exception as exc:
            self.errors.append(ValidationError(
                "error", "schema",
                f"Cannot read {yaml_path.name}: {exc}",
                path=str(yaml_path),
            ))
            return

        try:
            rel = yaml_path.relative_to(self._app_root)
        except ValueError:
            rel = yaml_path

        kind = declared_kind(data)
        if kind is None or schema_path_for_kind(kind) is None:
            return

        result = validate_data(
            data,
            source=str(rel),
            kind=kind,
            strict=self.strict,
            base_dir=yaml_path.parent.resolve(),
            resolve_refs=True,
        )

        for issue in result.issues:
            target = self.warnings if issue.level == "warning" else self.errors
            target.append(ValidationError(
                issue.level if issue.level in ("error", "warning") else "error",
                "schema",
                f"[{rel}] {issue.message}",
                path=issue.path or None,
            ))

        if result.ok and not any(i.level == "error" for i in result.issues):
            self.info.append(ValidationError(
                "info", "schema",
                f"Schema OK: {rel}",
            ))

        if self.strict and kind == "agent":
            self._check_agent_recommended(data, str(rel))

    def _check_agent_recommended(self, data: Dict, source: str) -> None:
        """Emit strict-mode warnings for missing recommended agent fields."""
        meta = data.get("metadata", {})
        spec = data.get("spec", {})
        agent_id = meta.get("name", source)

        if not spec.get("role", {}).get("description"):
            self.warnings.append(ValidationError(
                "warning", "agent",
                f"Agent '{agent_id}' has no spec.role.description — "
                "add a routing-optimised one-liner so the orchestrator LLM "
                "knows when to delegate to this agent.",
                path=f"{source}: $.spec.role.description",
            ))

        if not spec.get("design_pattern"):
            self.warnings.append(ValidationError(
                "warning", "agent",
                f"Agent '{agent_id}' does not declare spec.design_pattern — "
                "defaulting to 'react'. Declare it explicitly for clarity.",
                path=f"{source}: $.spec.design_pattern",
            ))

        if not meta.get("description"):
            self.warnings.append(ValidationError(
                "warning", "agent",
                f"Agent '{agent_id}' has no metadata.description — "
                "add one as a human-readable fallback for dashboards and logs.",
                path=f"{source}: $.metadata.description",
            ))
    
    def _load_spec(self) -> bool:
        """Load MAS specification from a JSON or YAML file.

        YAML files (``*.yaml``, ``*.yml``) are loaded via ``load_mas_config``
        which resolves agent refs and produces a JSON-compatible dict stored
        in ``MASManifest._raw``.  That dict is then validated by the standard
        path so no changes to downstream validation methods are required.
        """
        suffix = Path(self.spec_path).suffix.lower()
        if suffix in (".yaml", ".yml"):
            return self._load_spec_yaml()
        return self._load_spec_json()

    def _load_spec_json(self) -> bool:
        """Load from a JSON file."""
        try:
            with open(self.spec_path) as f:
                self.spec = json.load(f)
            self.info.append(ValidationError("info", "structure", f"Loaded spec: {self.spec_path}"))
            return True
        except FileNotFoundError:
            self.errors.append(ValidationError(
                "error", "structure",
                f"Spec file not found: {self.spec_path}"
            ))
            return False
        except json.JSONDecodeError as e:
            self.errors.append(ValidationError(
                "error", "structure",
                f"Invalid JSON: {e}",
                path=f"line {e.lineno}"
            ))
            return False

    def _load_spec_yaml(self) -> bool:
        """Load from a mas/v1 YAML file (``mas.yaml`` or ``kind: Overlay``) via load_mas_config.

        When the path is an overlay, the sibling/parent ``mas.yaml`` is loaded via
        ``load_mas_config`` and patch-specific fields (telemetry, capabilities,
        mocking, test_knowledge) are applied on top.
        """
        from mas.runtime.spec.source import load_yaml_file

        try:
            _peek = load_yaml_file(Path(self.spec_path))
        except Exception as e:
            self.errors.append(ValidationError("error", "structure", f"Failed to read YAML: {e}"))
            return False

        def is_overlay_kind(k): return str(k or '').lower() in ('overlay', 'patch', '')
#
        if isinstance(_peek, dict) and is_overlay_kind(_peek.get("kind")):
            return self._load_spec_yaml_overlay(_peek)

        # Normal App / Workflow / MAS path.
        # validate=False: we want to load even if separation rules are violated so
        # that _validate_manifest_separation() can report each violation individually.
        try:
            from mas.lab.manifest.load import load_mas_config
            manifest = load_mas_config(self.spec_path, validate=False)
            self.spec = manifest._raw
            self.info.append(ValidationError(
                "info", "structure",
                f"Loaded OASF YAML spec ({len(manifest._raw.get('agents', []))} agents): {self.spec_path}"
            ))
            return True
        except FileNotFoundError:
            self.errors.append(ValidationError("error", "structure", f"Spec file not found: {self.spec_path}"))
            return False
        except Exception as e:
            self.errors.append(ValidationError("error", "structure", f"Failed to load YAML spec: {e}"))
            return False

    def _load_spec_yaml_overlay(self, overlay: dict) -> bool:
        """Load a ``kind: Overlay`` by delegating to the shared loader utility."""
        from mas.lab.manifest.load import load_overlay_as_spec
        try:
            # validate=False — separation checks happen in _validate_manifest_separation()
            self.spec = load_overlay_as_spec(self.spec_path, overlay)
            name = overlay.get("metadata", {}).get("name") or Path(self.spec_path).stem
            agent_count = len(self.spec.get("agents", []))
            self.info.append(ValidationError(
                "info", "structure",
                f"Loaded overlay '{name}' over mas.yaml ({agent_count} agents)"
            ))
            return True
        except FileNotFoundError as e:
            self.errors.append(ValidationError("error", "structure", str(e)))
            return False
        except Exception as e:
            self.errors.append(ValidationError("error", "structure", f"Failed to load overlay spec: {e}"))
            return False

    
    def _validate_structure(self):
        """Semantic cross-reference checks for the loaded MAS spec.

        Required/type checks are handled by JSON Schema in ``_validate_schemas``.
        This method only adds checks that JSON Schema cannot express:
        - entry_agent must reference an ID that exists in the agents list.
        - mas.description empty warning (informational quality check).
        """
        if not self.spec:
            return

        mas = self.spec.get("mas", {})

        if self.strict and not mas.get("description"):
            self.warnings.append(ValidationError(
                "warning", "structure",
                "mas.description is empty — consider adding a concise description "
                "of what the MAS does and who its entry agent is.",
                path="$.mas.description",
            ))

        # Cross-reference: entry_agent must appear in the agents list.
        entry_id = mas.get("entry_agent", "")
        if entry_id and "agents" in self.spec:
            agent_ids = {a.get("id") for a in self.spec.get("agents", [])}
            if entry_id not in agent_ids:
                self.errors.append(ValidationError(
                    "error", "agent",
                    f"entry_agent '{entry_id}' not found in agents list",
                    path="$.mas.entry_agent",
                ))
    
    def _check_file_references(self):
        """Check that all file references exist."""
        if not self.spec:
            return
        
        # Check memory stores
        if "memory_stores" in self.spec:
            for key, rel_path in self.spec["memory_stores"].items():
                self._check_file_ref(rel_path, "memory", f"$.memory_stores.{key}")
        
        # Check agent artifacts
        if "agents" in self.spec:
            for i, agent in enumerate(self.spec["agents"]):
                agent_id = agent.get("id", f"agent_{i}")
                
                # Skills
                if "skills_ref" in agent:
                    self._check_file_ref(agent["skills_ref"], "agent", f"$.agents[{i}].skills_ref")
                
                # tools_ref is a logical name resolved by the ToolRegistry at runtime — not a
                # file path.  File-existence cannot be checked here without an infra manifest.
                # Validated structurally by the agent JSON Schema (must be a plain string).
                
                # Prompts
                if "prompt_ref" in agent:
                    self._check_file_ref(agent["prompt_ref"], "agent", f"$.agents[{i}].prompt_ref")
    
    def _check_file_ref(self, rel_path: str, category: str, json_path: str):
        """Check a single file reference."""
        # Resolve relative to base_dir
        full_path = self.base_dir / rel_path
        
        if not full_path.exists():
            self.errors.append(ValidationError(
                "error", "reference",
                f"File not found: {rel_path}",
                path=json_path
            ))
        else:
            self.info.append(ValidationError(
                "info", "reference",
                f"Found: {rel_path}",
                path=json_path
            ))
    
    def _validate_agents(self):
        """Semantic agent validation — duplicate ID check only.

        Required fields (id, name) and type checks are handled by JSON Schema
        in ``_validate_schemas``.  Recommended-field warnings are emitted by
        ``_check_agent_recommended`` during the schema pass, on the source YAML.
        """
        if not self.spec or "agents" not in self.spec:
            return

        agent_ids: set = set()
        for i, agent in enumerate(self.spec["agents"]):
            agent_id = agent.get("id")
            if not agent_id:
                continue  # missing id is already reported by schema pass
            if agent_id in agent_ids:
                self.errors.append(ValidationError(
                    "error", "agent",
                    f"Duplicate agent ID: '{agent_id}'",
                    path=f"$.agents[{i}].id",
                ))
            agent_ids.add(agent_id)
    
    def _check_ontologies(self):
        """Validate ontology references."""
        if not self.spec:
            return
        
        # Check global ontology negotiation
        if "ontology_negotiation" in self.spec:
            ont_neg = self.spec["ontology_negotiation"]
            if ont_neg.get("enabled") and "authority_urls" in ont_neg:
                urls = ont_neg["authority_urls"]
                if not urls or len(urls) == 0:
                    self.warnings.append(ValidationError(
                        "warning", "ontology",
                        "Ontology negotiation enabled but no authority URLs provided",
                        path="$.ontology_negotiation.authority_urls"
                    ))
                else:
                    self.info.append(ValidationError(
                        "info", "ontology",
                        f"Found {len(urls)} ontology authority URLs"
                    ))
        
        # Check agent-specific ontologies
        if "agents" in self.spec:
            for i, agent in enumerate(self.spec["agents"]):
                if "ontologies" in agent:
                    agent_id = agent.get("id", f"agent_{i}")
                    onts = agent["ontologies"]
                    if isinstance(onts, list) and len(onts) > 0:
                        self.info.append(ValidationError(
                            "info", "ontology",
                            f"Agent '{agent_id}' uses {len(onts)} ontologies"
                        ))
    

    # ------------------------------------------------------------------
    # Manifest separation validation
    # ------------------------------------------------------------------

    def _validate_manifest_separation(self) -> None:
        """Enforce model/access separation rules across all YAML manifests.

        Walks the directory tree rooted at ``spec_path.parent`` and validates:

        * ``mas.yaml`` → :class:`MASManifestValidator`
        * ``agents/**/agent.yaml`` → :class:`AgentManifestValidator`
        * ``overlays/*.yaml`` → :class:`OverlayManifestValidator`
        * ``flavours/*.yaml`` → :class:`FlavourManifestValidator`

        Each violation is recorded as an individual ``ValidationError`` with
        category ``"separation"`` rather than a single opaque exception.
        """
        from mas.ctl.validate.separation import (
            AgentSeparationValidator,
            FlavourSeparationValidator,
            MASSeparationValidator,
            OverlaySeparationValidator,
        )
        from mas.runtime.spec.source import load_yaml_file

        root = self._app_root

        targets = [
            (root.glob("mas.yaml"),              MASSeparationValidator,     "mas"),
            (root.rglob("agents/**/agent.yaml"),  AgentSeparationValidator,   "agent"),
            (root.glob("overlays/*.yaml"),        OverlaySeparationValidator, "overlay"),
            (root.glob("flavours/*.yaml"),        FlavourSeparationValidator, "flavour"),
        ]

        checked = 0
        for paths, validator_cls, kind_label in targets:
            for yaml_path in sorted(paths):
                try:
                    data = load_yaml_file(yaml_path)
                except Exception as exc:
                    self.warnings.append(ValidationError(
                        "warning", "separation",
                        f"Could not read {yaml_path.relative_to(root)}: {exc}",
                    ))
                    continue

                violations = validator_cls.collect_violations(data)
                if not violations:
                    checked += 1
                    self.info.append(ValidationError(
                        "info", "separation",
                        f"{kind_label}: {yaml_path.relative_to(root)} — OK",
                    ))
                else:
                    for violation in violations:
                        self.errors.append(ValidationError(
                            "error", "separation",
                            violation,
                            path=str(yaml_path.relative_to(root)),
                        ))

        if checked:
            self.info.append(ValidationError(
                "info", "separation",
                f"Manifest separation: validated {checked} file(s) — no violations",
            ))
