#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

def discover_scenario_stems(scenarios_dir: Path) -> List[str]:
    """Return sorted scenario stems from *scenarios_dir*.

    Supports:
    - Flat overlay files: ``<dir>/<id>.yaml``
    - Subdirectory apps:  ``<dir>/<id>/mas.yaml``

    If multiple formats exist for the same stem, they are deduplicated.
    """
    stems: set[str] = set()
    if not scenarios_dir.exists():
        return []
    for p in scenarios_dir.glob("*.yaml"):
        if p.stem != "mas":
            stems.add(p.stem)
    for p in scenarios_dir.iterdir():
        if p.is_dir() and (p / "mas.yaml").exists():
            stems.add(p.name)
    return sorted(stems)


def load_scenario_config(
    scenarios_dir: Path,
    scenario_id: str,
    mas_yaml: Optional[Path] = None,
) -> tuple[dict, Path]:
    """Load a scenario config from *scenarios_dir*, overlay-first.

    Resolution order:
    1. ``<scenarios_dir>/<scenario_id>.yaml``  — MAS overlay applied on top
       of the base ``mas.yaml``.  By default ``mas.yaml`` is expected at
       ``<scenarios_dir>/../mas.yaml``; pass *mas_yaml* to override this when
       the experiment keeps overlays in a subdirectory that is not adjacent to
       the shared ``mas.yaml`` (e.g. ``experiments/02-injection/overlays/``).

    Overlay spec fields propagated into the merged config:

    * ``spec.patch.capabilities``  → ``config["capabilities"]``  (merge/update)
    * ``spec.patch.telemetry``     → ``config["mas"]["telemetry"]`` (merge/update)
    * ``spec.patch.params``        → ``config["params"]`` (replace)
      Domain-specific key/value pairs opaque to the runner.  Consumers (e.g.
      the demo server) may extract and act on them — for instance by writing
      ``artifacts/scene.yaml`` from ``params.incident_fixture``.
    * ``spec.patch.tools_remove``  → ``config["tools_remove"]`` (replace list)
    * ``spec.patch.skills_exclude``→ ``config["skills_exclude"]`` (replace list)

    Returns
    -------
    (config_dict, base_path)
        *config_dict* is the fully merged MAS config ready for ``MasRuntime``.
        *base_path* is the anchor for relative-path resolution (the ``mas.yaml``
        parent for overlays).

    Raises
    ------
    FileNotFoundError
        When no ``.yaml`` overlay is found.
    """
    # 1. Prefer overlay file — flat or subdirectory layout
    overlay_path = scenarios_dir / f"{scenario_id}.yaml"
    # apps/<id>/mas.yaml  (subdirectory layout used by apps/)
    if not overlay_path.exists():
        _subdir_path = scenarios_dir / scenario_id / "mas.yaml"
        if _subdir_path.exists():
            overlay_path = _subdir_path

    if overlay_path.exists():
        import yaml as _yaml
        from mas.lab.manifest.load import load_mas_config
        from mas.runtime.spec.source import load_yaml_mapping

        overlay = load_yaml_mapping(overlay_path)

        # Distinguish standalone MAS manifests from scenario overlays.
        # Files with ``kind: MAS`` (or ``kind: Workflow``) are full manifests
        # that define their own agents and topology — load them directly
        # instead of patching a base mas.yaml.
        _overlay_kind = (overlay or {}).get("kind", "")
        if _overlay_kind in ("MAS", "Workflow"):
            mas_manifest = load_mas_config(overlay_path, validate=False)
            config = dict(mas_manifest._raw)
            # Store raw overlay for cache key coverage even on full-manifest overlays.
            config["_overlay_hash_input"] = [overlay]
            return config, overlay_path

        # Resolve mas.yaml: explicit argument > sibling of configs_dir
        _mas_yaml: Path = mas_yaml if mas_yaml is not None else scenarios_dir.parent / "mas.yaml"
        if not _mas_yaml.exists():
            raise FileNotFoundError(
                f"mas.yaml not found for overlay {overlay_path}: expected at {_mas_yaml}"
            )
        mas_yaml = _mas_yaml
        # validate=False: allow single-agent Workflow manifests in lab overlay contexts.
        mas_manifest = load_mas_config(mas_yaml, validate=False)  # type: ignore[arg-type]
        config = dict(mas_manifest._raw)

        # Inject overlay plugins into each agent in the MAS config so that
        # MasRuntime._build_agents can load them at runtime.
        # Supports both:
        #   spec.plugins         (direct overlay format)
        #   spec.patch.plugins   (kind:Patch format used by locomo mem0 overlays)
        overlay_spec = overlay.get("spec", {}).get("patch", {}) if overlay else {}
        if overlay:
            _overlay_agent_plugins = (
                overlay.get("spec", {}).get("plugins")
                or overlay_spec.get("plugins")
            )
            if _overlay_agent_plugins and config.get("agents"):
                for _agent_cfg in config["agents"]:
                    _existing = list(_agent_cfg.get("plugins") or [])
                    _agent_cfg["plugins"] = _existing + list(_overlay_agent_plugins)

        if "capabilities" in overlay_spec:
            config.setdefault("capabilities", {}).update(overlay_spec["capabilities"])
        if "telemetry" in overlay_spec:
            config.setdefault("mas", {}).setdefault("telemetry", {}).update(
                overlay_spec["telemetry"]
            )
        # Domain-specific params — opaque to the runtime, consumed by the caller
        # (e.g. the demo server writes artifacts/scene.yaml from params.incident_fixture).
        if "params" in overlay_spec:
            config["params"] = overlay_spec["params"]
        # Tool / skill filtering declared at overlay level
        if "tools_remove" in overlay_spec:
            config["tools_remove"] = overlay_spec["tools_remove"]
        if "skills_exclude" in overlay_spec:
            config["skills_exclude"] = overlay_spec["skills_exclude"]
        # skills_include: global skills to ADD to every agent (array-append semantics
        # that RFC 7396 Merge Patch cannot express natively).
        if "skills_include" in overlay_spec:
            config["skills_include"] = overlay_spec["skills_include"]
        # Per-agent overrides: spec.agents.<id>.role.instructions / design_pattern / tools_remove
        if "agents" in overlay_spec:
            overlay_agents: dict = overlay_spec["agents"]
            agents_list: list = config.get("agents", [])
            for agent_cfg in agents_list:
                agent_id = agent_cfg.get("id", "")
                per_agent = overlay_agents.get(agent_id, {})
                if not per_agent:
                    continue
                # New schema: role.instructions → written to role_instructions for runtime
                _role_override = per_agent.get("role") or {}
                if isinstance(_role_override, dict) and _role_override.get("instructions"):
                    agent_cfg["role_instructions"] = _role_override["instructions"]
                    logger.info("[overlay] agent '%s': role.instructions overridden (scenario=%s)", agent_id, scenario_id)
                # Legacy flat key (kept for backward compat)
                for key in ("role_instructions", "design_pattern"):
                    if key in per_agent:
                        agent_cfg[key] = per_agent[key]
                        logger.info("[overlay] agent '%s': %s overridden (scenario=%s)", agent_id, key, scenario_id)
                if "tools_remove" in per_agent:
                    existing = set(agent_cfg.get("tools_remove") or [])
                    added = set(per_agent["tools_remove"]) - existing
                    agent_cfg["tools_remove"] = sorted(existing | set(per_agent["tools_remove"]))
                    if added:
                        logger.info("[overlay] agent '%s': tools_remove += %s (scenario=%s)", agent_id, sorted(added), scenario_id)
                # Per-agent tools: merge new tool names into spec_tools.
                if "tools" in per_agent:
                    existing_tools = list(agent_cfg.get("spec_tools") or [])
                    for t in per_agent["tools"]:
                        if t not in existing_tools:
                            existing_tools.append(t)
                    agent_cfg["spec_tools"] = existing_tools
                    logger.info("[overlay] agent '%s': spec_tools = %s (scenario=%s)", agent_id, existing_tools, scenario_id)
                # Per-agent skills (add): merge new skill names.
                if "skills" in per_agent:
                    existing_skills = list(agent_cfg.get("skills") or [])
                    existing_set = set(existing_skills)
                    for sk in (per_agent["skills"] or []):
                        if sk not in existing_set:
                            existing_skills.append(sk)
                            existing_set.add(sk)
                    agent_cfg["skills"] = existing_skills
                    logger.info("[overlay] agent '%s': skills = %s (scenario=%s)", agent_id, existing_skills, scenario_id)
                # Per-agent llm override: deep-merge so individual keys can change.
                if "llm" in per_agent:
                    if isinstance(per_agent["llm"], dict):
                        base_llm = agent_cfg.get("llm") or {}
                        base_llm.update(per_agent["llm"])
                        agent_cfg["llm"] = base_llm
                        # Also keep flat llm_model in sync for runtimes that read it
                        if "model" in per_agent["llm"]:
                            agent_cfg["llm_model"] = per_agent["llm"]["model"]
                    else:
                        agent_cfg["llm"] = per_agent["llm"]
                    logger.info("[overlay] agent '%s': llm overridden (scenario=%s)", agent_id, scenario_id)
            unresolved = set(overlay_agents) - {a.get("id") for a in agents_list}
            if unresolved:
                logger.warning(
                    "[overlay] spec.agents keys not matched in mas.yaml agents: %s",
                    ", ".join(sorted(unresolved)),
                )

        # agents_remove: strip agents by ID.  Runs after per-agent overrides so that
        # agents_add can re-introduce a differently-configured variant of the same ID.
        agents_remove_ids: list = overlay_spec.get("agents_remove", []) or []
        if agents_remove_ids and config.get("agents"):
            _remove_set = set(agents_remove_ids)
            config["agents"] = [
                a for a in config["agents"] if a.get("id") not in _remove_set
            ]
            logger.debug("[overlay] agents_remove: %s (scenario=%s)", agents_remove_ids, scenario_id)

        # agents_add: append new agent entries.  Idempotent — entries whose id
        # already exists in the (post-remove) list are skipped.
        # When an entry has a ``ref`` field, load and expand via load_agent_runtime_entry.
        agents_add_list: list = overlay_spec.get("agents_add", []) or []
        if agents_add_list:
            from mas.lab.manifest.load import load_agent_runtime_entry
            from mas.runtime.spec.source import resolve_yaml_path
            # mas_yaml is guaranteed to be set at this point (overlay path is used)
            _mas_base = mas_yaml.parent  # type: ignore[union-attr]
            _existing_ids = {a.get("id") for a in config.get("agents", [])}
            for _new_agent in agents_add_list:
                _aid = _new_agent.get("id")
                if _aid in _existing_ids:
                    continue
                _ref = _new_agent.get("ref")
                if _ref:
                    # Resolve ref relative to mas.yaml parent and expand into
                    # a fully-materialised runtime dict (role_instructions,
                    # llm_model, spec_tools, _agent_dir, …).
                    _ref_path = resolve_yaml_path(str(_ref), _mas_base)
                    try:
                        _expanded = load_agent_runtime_entry(_ref_path, agent_id=_aid)
                        config.setdefault("agents", []).append(_expanded)
                    except Exception as _e:
                        logger.warning(
                            "[overlay] agents_add '%s': failed to load ref %s: %s (scenario=%s)",
                            _aid, _ref, _e, scenario_id,
                        )
                        config.setdefault("agents", []).append(_new_agent)
                else:
                    # Inline agent entry (no ref): append as-is.
                    config.setdefault("agents", []).append(_new_agent)
                _existing_ids.add(_aid)
                logger.debug("[overlay] agents_add: %s (scenario=%s)", _aid, scenario_id)

        # Global design-pattern override: spec.patch.design_pattern → set
        # pattern_framework (and optional pattern_params) on ALL agents.
        # Ignores spec.target — applies to all agents in the MAS.
        dp_spec = overlay_spec.get("design_pattern")
        if dp_spec and config.get("agents"):
            dp_type = dp_spec.get("type", "react") if isinstance(dp_spec, dict) else str(dp_spec)
            dp_params = (dp_spec.get("config") or dp_spec.get("params") or {}) if isinstance(dp_spec, dict) else {}
            for _agent_cfg in config["agents"]:
                _agent_cfg["pattern_framework"] = dp_type
                if dp_params:
                    _agent_cfg.setdefault("pattern_params", {}).update(dp_params)
            logger.debug("[overlay] design_pattern set to '%s' for all agents (scenario=%s)", dp_type, scenario_id)

        # Workflow topology override: spec.patch.workflow → config["workflow"].
        if "workflow" in overlay_spec:
            config["workflow"] = overlay_spec["workflow"]
            # Sync mas.entry_agent: DynamicWorkflow reads config["mas"]["entry_agent"]
            # (set by yaml_mas.py from workflow.entry at load time) — keep in sync.
            _new_entry = overlay_spec["workflow"].get("entry")
            if _new_entry:
                config.setdefault("mas", {})["entry_agent"] = _new_entry
            logger.debug("[overlay] workflow overridden (scenario=%s)", scenario_id)

        # Governance policies injection: spec.governance → GovernancePolicyEngine
        # plugin injected into all agents.
        gov_spec = overlay.get("spec", {}).get("governance") if overlay else None
        if gov_spec and config.get("agents"):
            gov_plugin = {
                "module_path": "mas.runtime.contracts.governance.policy_engine",
                "class_name": "GovernancePolicyEngine",
                "priority": 10,
                "params": gov_spec,
            }
            for _agent_cfg in config["agents"]:
                _existing = list(_agent_cfg.get("plugins") or [])
                _agent_cfg["plugins"] = _existing + [gov_plugin]
            logger.debug("[overlay] governance policies injected (scenario=%s)", scenario_id)

        # Embed the full raw overlay in the config so _compute_run_hash captures
        # every overlay dimension automatically — including any fields not yet
        # handled by explicit overlay application above.  The hash function's
        # _materialize_config deep-copies the config dict, so _overlay_hash_input
        # flows into the SHA-256 payload without any extra plumbing.
        config["_overlay_hash_input"] = [overlay]

        return config, mas_yaml

    raise FileNotFoundError(
        f"Scenario '{scenario_id}' not found in {scenarios_dir} "
        f"(checked {scenario_id}.yaml)"
    )


def load_stacked_config(
    mas_yaml: Path,
    overlay_ids: "List[Union[str, dict]]",
    overlays_dir: Optional[Path] = None,
    *,
    base_dir: Optional[Path] = None,
) -> tuple[dict, Path]:
    """Stack multiple overlays in order on top of the base ``mas.yaml``.

    Kustomize-style: overlay files are read from *overlays_dir* (defaulting to
    ``<mas_yaml_parent>/overlays/``) and applied sequentially.  Each overlay
    merges its ``spec`` fields into the accumulated config using the same rules
    as :func:`load_scenario_config`.

    Parameters
    ----------
    mas_yaml:
        Absolute path to the ``mas.yaml`` manifest.
    overlay_ids:
        Ordered list of overlay entries.  Each entry is either a plain string
        (file stem resolved inside *overlays_dir*) or a ``{ref: path}`` dict
        whose path is resolved relative to *base_dir*.
    overlays_dir:
        Directory containing overlay YAML files.  When *None*, defaults to
        ``mas_yaml.parent / "overlays"``.  Pass an explicit path when the
        experiment keeps its overlays separate from the app (e.g. a lab
        referencing an app via ``mas.app``).
    base_dir:
        Root directory for resolving ``{ref: path}`` overlay entries.  When
        *None*, defaults to ``mas_yaml.parent``.

    Returns
    -------
    (config_dict, mas_yaml)
        *config_dict* is the fully merged MAS config ready for ``MasRuntime``.
        *mas_yaml* is returned as the base path (for relative-path resolution).

    Raises
    ------
    FileNotFoundError
        When ``mas_yaml`` or any overlay file is missing.
    """
    if not mas_yaml.exists():
        raise FileNotFoundError(f"mas.yaml not found: {mas_yaml}")

    from mas.lab.manifest.load import load_mas_config
    from mas.runtime.spec.source import load_yaml_mapping

    mas_manifest = load_mas_config(mas_yaml, validate=False)
    config = dict(mas_manifest._raw)

    _overlays_dir = overlays_dir if overlays_dir is not None else mas_yaml.parent / "overlays"
    _base_dir = base_dir if base_dir is not None else mas_yaml.parent
    _applied_overlays: list = []
    for overlay_entry in overlay_ids:
        if isinstance(overlay_entry, dict) and "ref" in overlay_entry:
            overlay_path = (_base_dir / overlay_entry["ref"]).resolve()
        else:
            overlay_id = str(overlay_entry)
            overlay_path = _overlays_dir / f"{overlay_id}.yaml"
        if not overlay_path.exists():
            raise FileNotFoundError(
                f"Overlay '{overlay_entry}' not found: {overlay_path}"
            )
        overlay = load_yaml_mapping(overlay_path)
        _overlay_kind = (overlay or {}).get("kind", "")
        if _overlay_kind in ("MAS", "Workflow"):
            mas_manifest = load_mas_config(overlay_path, validate=False)
            config = dict(mas_manifest._raw)
            _applied_overlays = [overlay]
            config["_overlay_hash_input"] = _applied_overlays
            return config, overlay_path

        overlay_spec = overlay.get("spec", {}).get("patch", {})
        if "capabilities" in overlay_spec:
            config.setdefault("capabilities", {}).update(overlay_spec["capabilities"])
        if "telemetry" in overlay_spec:
            config.setdefault("mas", {}).setdefault("telemetry", {}).update(
                overlay_spec["telemetry"]
            )
        if "params" in overlay_spec:
            config["params"] = overlay_spec["params"]
        if "tools_remove" in overlay_spec:
            config["tools_remove"] = overlay_spec["tools_remove"]
        if "skills_exclude" in overlay_spec:
            config["skills_exclude"] = overlay_spec["skills_exclude"]
        if "skills_include" in overlay_spec:
            config["skills_include"] = overlay_spec["skills_include"]
        # Per-agent overrides: spec.agents.<id>.role.instructions / design_pattern / tools_remove
        if "agents" in overlay_spec:
            overlay_agents: dict = overlay_spec["agents"]
            agents_list: list = config.get("agents", [])
            for agent_cfg in agents_list:
                agent_id = agent_cfg.get("id", "")
                per_agent = overlay_agents.get(agent_id, {})
                if not per_agent:
                    continue
                # New schema: role.instructions → written to role_instructions for runtime
                _role_override = per_agent.get("role") or {}
                if isinstance(_role_override, dict) and _role_override.get("instructions"):
                    agent_cfg["role_instructions"] = _role_override["instructions"]
                # Legacy flat key (kept for backward compat)
                for key in ("role_instructions", "design_pattern"):
                    if key in per_agent:
                        agent_cfg[key] = per_agent[key]
                if "tools_remove" in per_agent:
                    existing = set(agent_cfg.get("tools_remove") or [])
                    agent_cfg["tools_remove"] = sorted(existing | set(per_agent["tools_remove"]))
                if "tools" in per_agent:
                    existing_tools = list(agent_cfg.get("spec_tools") or [])
                    for t in per_agent["tools"]:
                        if t not in existing_tools:
                            existing_tools.append(t)
                    agent_cfg["spec_tools"] = existing_tools
                if "skills" in per_agent:
                    existing_skills = list(agent_cfg.get("skills") or [])
                    existing_set = set(existing_skills)
                    for sk in (per_agent["skills"] or []):
                        if sk not in existing_set:
                            existing_skills.append(sk)
                            existing_set.add(sk)
                    agent_cfg["skills"] = existing_skills
                if "llm" in per_agent:
                    if isinstance(per_agent["llm"], dict):
                        base_llm = agent_cfg.get("llm") or {}
                        base_llm.update(per_agent["llm"])
                        agent_cfg["llm"] = base_llm
                        if "model" in per_agent["llm"]:
                            agent_cfg["llm_model"] = per_agent["llm"]["model"]
                    else:
                        agent_cfg["llm"] = per_agent["llm"]

        # agents_remove: strip agents by ID.
        _agents_remove: list = overlay_spec.get("agents_remove", []) or []
        if _agents_remove and config.get("agents"):
            _rm_set = set(_agents_remove)
            config["agents"] = [a for a in config["agents"] if a.get("id") not in _rm_set]

        # agents_add: append new agent entries (idempotent by ID, ref-expanded).
        _agents_add: list = overlay_spec.get("agents_add", []) or []
        if _agents_add:
            from mas.lab.manifest.load import load_agent_runtime_entry
            from mas.runtime.spec.source import resolve_yaml_path
            _existing_ids = {a.get("id") for a in config.get("agents", [])}
            for _new_agent in _agents_add:
                _aid = _new_agent.get("id")
                if _aid in _existing_ids:
                    continue
                _ref = _new_agent.get("ref")
                if _ref:
                    _ref_path = resolve_yaml_path(str(_ref), mas_yaml.parent)
                    try:
                        _expanded = load_agent_runtime_entry(_ref_path, agent_id=_aid)
                        config.setdefault("agents", []).append(_expanded)
                    except Exception as _e:
                        logger.warning("[overlay] agents_add '%s': ref load failed: %s", _aid, _e)
                        config.setdefault("agents", []).append(_new_agent)
                else:
                    config.setdefault("agents", []).append(_new_agent)
                _existing_ids.add(_aid)

        # Global design-pattern override: spec.patch.design_pattern
        dp_spec = overlay_spec.get("design_pattern")
        if dp_spec and config.get("agents"):
            dp_type = dp_spec.get("type", "react") if isinstance(dp_spec, dict) else str(dp_spec)
            dp_params = (dp_spec.get("config") or dp_spec.get("params") or {}) if isinstance(dp_spec, dict) else {}
            for _agent_cfg in config["agents"]:
                _agent_cfg["pattern_framework"] = dp_type
                if dp_params:
                    _agent_cfg.setdefault("pattern_params", {}).update(dp_params)

        # Workflow topology override
        if "workflow" in overlay_spec:
            config["workflow"] = overlay_spec["workflow"]
            _new_entry = overlay_spec["workflow"].get("entry")
            if _new_entry:
                config.setdefault("mas", {})["entry_agent"] = _new_entry

        # Governance policies injection
        gov_spec = overlay.get("spec", {}).get("governance") if overlay else None
        if gov_spec and config.get("agents"):
            gov_plugin = {
                "module_path": "mas.runtime.contracts.governance.policy_engine",
                "class_name": "GovernancePolicyEngine",
                "priority": 10,
                "params": gov_spec,
            }
            for _agent_cfg in config["agents"]:
                _existing = list(_agent_cfg.get("plugins") or [])
                _agent_cfg["plugins"] = _existing + [gov_plugin]

        # Overlay-level plugins injection (spec.plugins)
        if overlay:
            _overlay_plugins = overlay.get("spec", {}).get("plugins")
            if _overlay_plugins and config.get("agents"):
                for _agent_cfg in config["agents"]:
                    _existing = list(_agent_cfg.get("plugins") or [])
                    _agent_cfg["plugins"] = _existing + list(_overlay_plugins)

        # Accumulate raw overlay for cache key (see load_scenario_config for rationale).
        _applied_overlays.append(overlay)

    # Embed all applied overlays so _compute_run_hash sees every dimension.
    config["_overlay_hash_input"] = _applied_overlays

    return config, mas_yaml

