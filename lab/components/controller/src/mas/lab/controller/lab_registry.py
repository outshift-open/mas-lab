#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unified lab registry — single point of contact for controller + UI discovery.

Extends the runtime object registry (``mas.registry``, plugin URN registry) with
lab-specific resources: libraries, experiments, pipelines, datasets, MAS apps,
and pipeline step types.
"""
from __future__ import annotations

import contextlib
import importlib.resources
import logging
import os
from importlib.metadata import entry_points as _entry_points
from pathlib import Path
from typing import Any, Dict, List, Optional

from mas.runtime.constants import WORKSPACE_CONFIG_FILENAME
from mas.runtime.spec.source import load_yaml_file

logger = logging.getLogger(__name__)


def _library_description(path: Path) -> str:
    for candidate in (path / "lab-config.yaml", path / "mas.yaml", path / "README.md"):
        if candidate.exists():
            try:
                if candidate.suffix == ".yaml":
                    data = load_yaml_file(candidate)
                    desc = (
                        data.get("description")
                        or data.get("metadata", {}).get("description")
                        or (data.get("lab") or {}).get("description")
                    )
                    if desc:
                        return str(desc).strip().splitlines()[0][:200]
                else:
                    return candidate.read_text(encoding="utf-8").splitlines()[0][:200]
            except Exception:
                pass
    return ""

from mas.runtime.agent_defaults import (
    CANONICAL_DEFAULT_DP,
    CANONICAL_DEFAULT_MODEL,
    agent_defaults as _agent_defaults,
    resolve_default_model,
)

_YAML_SUFFIXES = frozenset({".yaml", ".yml"})
"""Directories that group manifests by role (path convention — filenames are free)."""
_TYPED_DIRS = frozenset({"datasets", "overlays", "flavours", "infra", "apps"})
_DISCOVERY_SKIP_DIRS = _TYPED_DIRS | {".git", "node_modules", "__pycache__", ".cache"}

_MAS_MANIFEST_NAMES = ("mas.yaml", "mas-bench.yaml")

_REGISTRY: Optional["LabRegistry"] = None


def _is_yaml_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _YAML_SUFFIXES


def _iter_library_yaml(lib_dir: Path):
    """All YAML files under a library root (discovery walks content, not names)."""
    if not lib_dir.is_dir():
        return
    for path in sorted(lib_dir.rglob("*")):
        if _is_yaml_file(path):
            yield path


def _iter_manifest_files(lib_dir: Path, expected_kind: str, *, parent_dir: str | None = None):
    """Yield YAML files whose declared kind matches *expected_kind*."""
    seen: set[Path] = set()
    for path in _iter_library_yaml(lib_dir):
        rel_parts = path.relative_to(lib_dir).parts
        if parent_dir is not None:
            if parent_dir not in rel_parts:
                continue
        elif _DISCOVERY_SKIP_DIRS.intersection(rel_parts):
            continue
        try:
            doc = load_yaml_file(path)
        except Exception:
            continue
        from mas.ctl.validate.schemas import declared_kind

        if declared_kind(doc) != expected_kind:
            continue
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            yield path


class LabRegistry:
    """Lab-facing registry: runtime objects + workspace libraries + lab artifacts."""

    def __init__(self, workspace: Any = None) -> None:
        self._workspace = workspace
        self._libraries: Dict[str, Path] = {}
        self._library_sources: Dict[str, str] = {}
        self.refresh()

    def refresh(self) -> None:
        self._libraries, self._library_sources = self._discover_library_paths()
        self._log_discovery()

    # ── Unified query API (UI / CLI / daemon) ─────────────────────────────
    #
    # ``spec_key`` matches agent manifest ``spec.<key>`` (e.g. design_pattern).
    # Runtime spec keys delegate to :func:`mas.runtime.registry.get_registry`.
    # Lab-only keys (pipeline_step, experiment, …) are resolved here.

    @staticmethod
    def _runtime_spec_keys() -> frozenset[str]:
        from mas.runtime.registry import SPEC_KEYS

        return frozenset(SPEC_KEYS)

    def _runtime_registry(self):
        from mas.runtime.registry import get_registry

        return get_registry()

    def resolve(
        self,
        spec_key: str,
        binding: dict | None = None,
        *,
        manifest: dict | None = None,
    ) -> Any:
        """Resolve and instantiate ``spec.<spec_key>`` (runtime) or lab artifact."""
        if spec_key in self._runtime_spec_keys():
            return self._runtime_registry().create(spec_key, binding, manifest=manifest)
        raise KeyError(f"LabRegistry.resolve: unknown spec key {spec_key!r}")

    def list(self, spec_key: str | None = None) -> Any:
        """List plugins or artifacts. *spec_key* = manifest ``spec.<key>`` name."""
        if spec_key is None:
            return self.catalog()
        if spec_key in self._runtime_spec_keys():
            return self._runtime_registry().list(spec_key)
        if spec_key == "pipeline_step":
            return self.pipeline_step_types()
        raise KeyError(f"LabRegistry.list: unknown spec key {spec_key!r}")

    def runtime_objects(self, kind: str) -> Dict[str, Path]:
        """Objects from ``mas.<kind>s`` entry points (app, dataset, tool)."""
        try:
            from mas.registry import list_names, get

            return {name: get(kind, name) for name in list_names(kind)}
        except ImportError:
            return {}

    def list_runtime_object_names(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for kind in ("app", "dataset", "tool"):
            out[kind] = sorted(self.runtime_objects(kind))
        return out

    # ── Agent / infra defaults ────────────────────────────────────────────

    def default_model(self) -> str:
        """Workspace default model (logical default, not infra)."""
        return resolve_default_model(self._workspace)

    def agent_defaults(self) -> Dict[str, Any]:
        return _agent_defaults(self._workspace)

    # ── Libraries ───────────────────────────────────────────────────────

    def library_paths(self) -> Dict[str, Path]:
        return dict(self._libraries)

    def libraries(self) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        for slug, path in sorted(self._libraries.items()):
            items.append(
                {
                    "dir": slug,
                    "name": slug.replace("-", " ").replace("_", " ").title(),
                    "description": _library_description(path),
                }
            )
        return items

    def library_root(self, library: str) -> Path:
        root = self._libraries.get(library)
        if root is None:
            raise KeyError(f"Library {library!r} not found")
        return root

    def catalog(self) -> Dict[str, Any]:
        """Full registry snapshot for ``GET /api/registry``."""
        runtime = self._runtime_registry()
        spec_catalog = {
            key: runtime.list(key) for key in sorted(self._runtime_spec_keys())
        }
        return {
            "runtime": self.list_runtime_object_names(),
            "spec": spec_catalog,
            "pipeline_steps": self.pipeline_step_types(),
            "libraries": [lib["dir"] for lib in self.libraries()],
            "defaults": self.agent_defaults(),
        }

    # ── Library artifacts ───────────────────────────────────────────────

    def list_experiments(self, library: str) -> List[Dict[str, Any]]:
        root = self.library_root(library)
        return [self._parse_experiment_metadata(p, root) for p in self._iter_experiment_files(root)]

    def list_pipelines(self, library: str) -> List[Dict[str, Any]]:
        root = self.library_root(library)
        return [self._parse_pipeline_metadata(p, root) for p in self._iter_pipeline_files(root)]

    def list_datasets(self, library: str) -> List[Dict[str, str]]:
        root = self.library_root(library)
        datasets: List[Dict[str, str]] = []
        for path in self._iter_dataset_files(root):
            rel = str(path.relative_to(root))
            datasets.append(
                {
                    "name": path.name,
                    "path": rel,
                    "description": self._dataset_description(path),
                }
            )
        return datasets

    def list_overlays(self, library: str) -> List[Dict[str, str]]:
        root = self.library_root(library)
        overlays: List[Dict[str, str]] = []
        for path in self._iter_overlay_files(root):
            rel = str(path.relative_to(root))
            entry: Dict[str, str] = {
                "name": path.stem,
                "filename": path.name,
                "path": rel,
            }
            try:
                data = load_yaml_file(path)
                meta = data.get("metadata", {})
                entry["description"] = str(meta.get("description", "") or "")
                entry["namespace"] = str(data.get("x-namespace", "global") or "global")
            except Exception:
                entry["description"] = ""
                entry["namespace"] = "global"
            overlays.append(entry)
        return overlays

    def collect_mas_resources(self, library: str) -> Dict[str, Dict[str, Any]]:
        # Only discover apps from the library filesystem.  The mas.apps
        # entry-point registry is a separate discovery mechanism used by
        # CLI / experiment resolution; mixing it in here would create
        # duplicates and break CRUD operations that expect filesystem paths.
        root = self.library_root(library)
        return self._collect_mas_resources(root)

    def list_all_experiments(self) -> List[Dict[str, Any]]:
        """All experiment definitions across discovered libraries."""
        items: List[Dict[str, Any]] = []
        for slug in sorted(self._libraries):
            for exp in self.list_experiments(slug):
                items.append({**exp, "library": slug})
        return items

    def discovery_report(self) -> Dict[str, Any]:
        """Snapshot of paths scanned and libraries resolved (for debugging / UI)."""
        ws_root = self._workspace_root()
        return {
            "workspace_root": str(ws_root) if ws_root else None,
            "mas_workspace_root_env": os.environ.get("MAS_WORKSPACE_ROOT") or None,
            "cwd": str(Path.cwd()),
            "labs_search_paths": self._labs_search_paths(),
            "libraries": [
                {
                    "slug": slug,
                    "path": str(path),
                    "source": self._library_sources.get(slug, "unknown"),
                }
                for slug, path in sorted(self._libraries.items())
            ],
            "runtime_apps": sorted(self.runtime_objects("app")),
            "runtime_datasets": sorted(self.runtime_objects("dataset")),
        }

    def pipeline_step_types(self) -> Dict[str, Any]:
        try:
            from mas.lab.benchmark.pipeline import get_step_registry

            registry = get_step_registry()
            step_types = []
            categories: Dict[str, dict] = {}
            for step_id, cls in sorted(registry.items()):
                doc = (cls.__doc__ or "").strip().split("\n")[0].strip()
                category = getattr(cls, "CATEGORY", "general")
                step_types.append(
                    {
                        "type": step_id,
                        "label": step_id.replace("_", " ").title(),
                        "description": doc,
                        "phase": getattr(cls, "PHASE", "post"),
                        "category": category,
                        "requires": getattr(cls, "REQUIRES", None),
                        "config": {},
                    }
                )
                categories.setdefault(
                    category, {"id": category, "label": category.title(), "color": "#888"}
                )
            return {"step_types": step_types, "categories": list(categories.values())}
        except Exception as exc:
            logger.debug("pipeline step types unavailable: %s", exc)
            return {"step_types": [], "categories": []}

    # ── Discovery internals ─────────────────────────────────────────────

    def _workspace_root(self) -> Optional[Path]:
        if self._workspace is None:
            try:
                from mas.lab.workspace import WorkspaceConfig

                ws = WorkspaceConfig.load()
                if ws.found and ws._path is not None:
                    return ws._path
            except Exception:
                return None
            return None
        base = getattr(self._workspace, "_path", None)
        return Path(base) if base is not None else None

    def _labs_search_paths(self) -> List[str]:
        if self._workspace is not None:
            mas_lab = getattr(self._workspace, "_data", {}).get("mas_lab") or {}
            paths = mas_lab.get("labs_search_paths")
            if paths:
                return [paths] if isinstance(paths, str) else list(paths)
            if hasattr(self._workspace, "mas_lab"):
                return list(self._workspace.mas_lab.labs_search_paths)
        try:
            from mas.lab.workspace import WorkspaceConfig

            ws = WorkspaceConfig.load()
            if ws.found:
                mas_lab = ws._data.get("mas_lab") or {}
                paths = mas_lab.get("labs_search_paths")
                if paths:
                    return [paths] if isinstance(paths, str) else list(paths)
        except Exception:
            pass
        return ["labs"]

    def _discover_library_paths(self) -> tuple[Dict[str, Path], Dict[str, str]]:
        libraries: Dict[str, Path] = {}
        sources: Dict[str, str] = {}

        def _add(slug: str, path: Path, source: str) -> None:
            resolved = path.resolve()
            if not resolved.exists():
                logger.debug("skip missing library %s at %s (%s)", slug, resolved, source)
                return
            if slug not in libraries:
                libraries[slug] = resolved
                sources[slug] = source
            else:
                logger.debug(
                    "library %s already mapped to %s; ignoring %s from %s",
                    slug,
                    libraries[slug],
                    resolved,
                    source,
                )

        for name, path in self.runtime_objects("app").items():
            _add(name, path, f"entry-point:mas.apps:{name}")

        try:
            from mas.library_roots import discover_library_roots

            for root in discover_library_roots():
                _add(root.name, root, "manifest_libraries")
        except Exception as exc:
            logger.debug("manifest library discovery failed: %s", exc)

        ws_root = self._workspace_root()
        if ws_root is not None:
            manifest_libs = getattr(self._workspace, "_data", {}).get("manifest_libraries") or {}
            if not manifest_libs and self._workspace is not None:
                manifest_libs = getattr(self._workspace, "_data", {}) or {}
                manifest_libs = manifest_libs.get("manifest_libraries") or {}
            for slug, rel in manifest_libs.items():
                _add(slug, ws_root / rel, f"manifest_libraries:{rel}")

            for rel in self._labs_search_paths():
                labs_dir = (ws_root / rel).resolve()
                if labs_dir.is_dir():
                    for path in sorted(labs_dir.glob("*.lab")):
                        _add(path.stem, path, f"labs_search_paths:{rel}")

        try:
            from mas.lab.workspace import find_workspace_root

            ws = find_workspace_root()
            if ws is not None:
                for rel in self._labs_search_paths():
                    labs_dir = ws / rel
                    if labs_dir.exists():
                        for path in sorted(labs_dir.glob("*.lab")):
                            _add(path.stem, path, f"workspace.find_workspace_root:{rel}")
        except Exception as exc:
            logger.debug("studio workspace discovery failed: %s", exc)

        cwd = Path.cwd().resolve()
        for directory in [cwd, *cwd.parents]:
            labs_dir = directory / "labs"
            if labs_dir.is_dir():
                for path in sorted(labs_dir.glob("*.lab")):
                    _add(path.stem, path, f"cwd-walk:{directory}")
            if (directory / WORKSPACE_CONFIG_FILENAME).exists():
                break

        try:
            from mas.lab.paths import labs_root

            labs = labs_root()
            if labs.exists():
                for path in sorted(labs.glob("*.lab")):
                    _add(path.stem, path, f"labs_root:{labs}")
        except Exception as exc:
            logger.debug("labs_root discovery failed: %s", exc)

        return libraries, sources

    def _log_discovery(self) -> None:
        report = self.discovery_report()
        logger.info(
            "LabRegistry: workspace_root=%s libraries=%d runtime_apps=%s",
            report.get("workspace_root"),
            len(report.get("libraries", [])),
            report.get("runtime_apps"),
        )
        for item in report.get("libraries", []):
            logger.info(
                "  library %-20s  %s  [%s]",
                item["slug"],
                item["path"],
                item["source"],
            )

    def _iter_experiment_files(self, lib_dir: Path):
        yield from _iter_manifest_files(lib_dir, "experiment")

    def _iter_pipeline_files(self, lib_dir: Path):
        yield from _iter_manifest_files(lib_dir, "pipeline")

    def _iter_dataset_files(self, lib_dir: Path):
        yield from _iter_manifest_files(lib_dir, "dataset", parent_dir="datasets")

    def _iter_overlay_files(self, lib_dir: Path):
        yield from _iter_manifest_files(lib_dir, "overlay", parent_dir="overlays")

    def _collect_mas_resources(self, lib_dir: Path) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        apps_dir = lib_dir / "apps"
        if apps_dir.exists():
            for app_folder in sorted(apps_dir.iterdir()):
                if not app_folder.is_dir():
                    continue
                mas_file = app_folder / "mas.yaml"
                if not mas_file.exists():
                    continue
                mas_name = app_folder.name
                entry: Dict[str, Any] = {
                    "mas_yaml": mas_file.read_text(encoding="utf-8"),
                    "agents": {},
                    "path": f"apps/{mas_name}/mas.yaml",
                }
                agents_dir = app_folder / "agents"
                if agents_dir.is_dir():
                    for af in sorted(agents_dir.glob("*.yaml")):
                        entry["agents"][af.stem] = af.read_text(encoding="utf-8")
                result[mas_name] = entry

        for mas_name in _MAS_MANIFEST_NAMES:
            for mas_file in sorted({lib_dir / mas_name, *lib_dir.rglob(mas_name)}):
                if not mas_file.is_file():
                    continue
                if "apps" in mas_file.parts and mas_file.name == "mas.yaml":
                    continue
                try:
                    doc = load_yaml_file(mas_file)
                except Exception:
                    doc = {}
                name = (doc.get("metadata") or {}).get("name") or mas_file.stem.replace(
                    "-bench", ""
                )
                if name in result:
                    continue
                mas_base = mas_file.parent
                result[str(name)] = {
                    "mas_yaml": mas_file.read_text(encoding="utf-8"),
                    "agents": self._load_agents_from_mas_refs(mas_base, doc),
                    "path": str(mas_file.relative_to(lib_dir)),
                }

        for mas_file in sorted(lib_dir.rglob("apps/*/mas.yaml")):
            if not mas_file.is_file():
                continue
            try:
                doc = load_yaml_file(mas_file)
            except Exception:
                doc = {}
            name = (doc.get("metadata") or {}).get("name") or mas_file.parent.name
            if str(name) in result:
                continue
            mas_base = mas_file.parent
            result[str(name)] = {
                "mas_yaml": mas_file.read_text(encoding="utf-8"),
                "agents": self._load_agents_from_mas_refs(mas_base, doc),
                "path": str(mas_file.relative_to(lib_dir)),
            }
        return result

    @staticmethod
    def _mas_resource_from_app_root(app_path: Path) -> Optional[Dict[str, Any]]:
        """Build a mas_resources entry from an installed app package directory."""
        for mas_file in (
            app_path / "mas.yaml",
            app_path / "mas-bench.yaml",
        ):
            if not mas_file.is_file():
                continue
            try:
                doc = load_yaml_file(mas_file)
            except Exception:
                doc = {}
            name = (doc.get("metadata") or {}).get("name") or mas_file.stem.replace("-bench", "")
            return {
                "mas_yaml": mas_file.read_text(encoding="utf-8"),
                "agents": LabRegistry._load_agents_from_mas_refs(app_path, doc),
                "path": str(mas_file.relative_to(app_path)),
                "source": "runtime-app",
            }
        return None

    @staticmethod
    def discover_bundled_infra() -> Dict[str, str]:
        """Infra bundle YAML from installed ``mas.runtime.manifest_libraries`` packages."""
        bundled: Dict[str, str] = {}
        for ep in _entry_points(group="mas.runtime.manifest_libraries"):
            try:
                pkg_name = ep.value
                libs_path = importlib.resources.files(pkg_name) / "libs" / ep.name
                with importlib.resources.as_file(libs_path) as root:
                    if not root.exists():
                        continue
                    for yaml_file in sorted(root.rglob("*.yaml")):
                        key = f"bundles/{ep.name}/{yaml_file.relative_to(root)}"
                        bundled[key] = yaml_file.read_text(encoding="utf-8")
            except Exception:
                continue
        return bundled

    @staticmethod
    def discover_workspace_infra(ws_root: Path) -> Dict[str, str]:
        """Workspace-level infra manifests (not nested under a single *.lab)."""
        infra: Dict[str, str] = {}
        infra_dir = ws_root / "infra"
        if infra_dir.is_dir():
            for path in sorted(infra_dir.glob("*.yaml")):
                infra[f"workspace/infra/{path.name}"] = path.read_text(encoding="utf-8")
            for path in sorted(infra_dir.glob("*.yml")):
                infra[f"workspace/infra/{path.name}"] = path.read_text(encoding="utf-8")
        return infra

    @staticmethod
    def _load_agents_from_mas_refs(lib_dir: Path, mas_doc: dict) -> Dict[str, str]:
        agents: Dict[str, str] = {}
        agency = (mas_doc.get("spec") or {}).get("agency") or {}
        for agent in agency.get("agents") or []:
            if not isinstance(agent, dict):
                continue
            agent_id = agent.get("id") or agent.get("name")
            ref = agent.get("ref")
            if not ref:
                continue
            agent_path = (lib_dir / ref).resolve()
            if agent_path.exists():
                agents[str(agent_id or agent_path.stem)] = agent_path.read_text(encoding="utf-8")
        return agents

    @staticmethod
    def _parse_experiment_metadata(path: Path, lib_dir: Path | None = None) -> Dict[str, Any]:
        rel = str(path.relative_to(lib_dir)) if lib_dir else str(path)
        entry: Dict[str, Any] = {"filename": path.name, "path": rel}
        try:
            doc = load_yaml_file(path)
            exp = doc.get("experiment") or doc
            entry["name"] = exp.get("name", path.stem)
            entry["description"] = exp.get("description", "")
            entry["version"] = exp.get("version", "")
            scenarios = exp.get("scenarios", [])
            entry["scenarios"] = [s.get("id", "") for s in scenarios if isinstance(s, dict)]
            dataset = exp.get("dataset", {})
            entry["dataset"] = dataset.get("path", "") if isinstance(dataset, dict) else ""
        except Exception:
            entry.update(
                name=path.stem,
                description="",
                version="",
                scenarios=[],
                dataset="",
            )
        return entry

    @staticmethod
    def _parse_pipeline_metadata(path: Path, lib_dir: Path | None = None) -> Dict[str, Any]:
        rel = str(path.relative_to(lib_dir)) if lib_dir else str(path)
        entry: Dict[str, Any] = {"filename": path.name, "path": rel}
        try:
            doc = load_yaml_file(path)
            block = doc.get("pipeline") if isinstance(doc.get("pipeline"), dict) else doc
            meta = block.get("metadata") or doc.get("metadata") or {}
            entry["name"] = meta.get("name") or block.get("name") or path.stem
            entry["description"] = meta.get("description") or block.get("description") or ""
            entry["bind"] = doc.get("x-bind", "")
            steps = block.get("steps") or (doc.get("spec") or {}).get("steps") or []
            entry["steps"] = [
                {
                    "name": s.get("name"),
                    "type": s.get("type"),
                    "depends_on": s.get("depends_on", []),
                }
                for s in steps
                if isinstance(s, dict)
            ]
            output = block.get("output") or (doc.get("spec") or {}).get("output") or {}
            entry["experiment"] = output.get("base_dir", "")
        except Exception:
            entry.update(name=path.stem, description="", bind="", steps=[], experiment="")
        return entry

    @staticmethod
    def _dataset_description(path: Path) -> str:
        try:
            data = load_yaml_file(path)
            return str(
                data.get("description") or (data.get("metadata") or {}).get("description") or ""
            )
        except Exception:
            return ""


def get_lab_registry(workspace: Any = None, *, refresh: bool = False) -> LabRegistry:
    """Return the process-wide :class:`LabRegistry` singleton."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = LabRegistry(workspace)
    elif refresh:
        _REGISTRY.refresh()
    return _REGISTRY


def reset_lab_registry() -> None:
    """Clear singleton (tests)."""
    global _REGISTRY
    _REGISTRY = None
