#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve infra/v1 refs to merged LLM proxy configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mas.runtime.spec.source import load_yaml_file, resolve_ref_with_search
from mas.runtime.xdg import mas_infra_dir
from mas.ctl.compose.models import ResolvedInfra
from mas.ctl.infra.env_resolve import resolve_manifest_values
from mas.ctl.infra.models import InfraManifest, ModelsSpec, ProxySpec
from mas.ctl.infra.pipeline_chain import BidirectionalInfraPipeline
from mas.ctl.libraries.bundles import list_manifest_libraries
from mas.ctl.workspace.config import UserConfig, WorkspaceConfig

logger = logging.getLogger(__name__)


class InfraResolveError(RuntimeError):
    """One or more infra refs or interceptors failed to load."""

    def __init__(self, errors: list[tuple[str, Exception]]) -> None:
        self.errors = list(errors)
        parts = [f"{ref!r}: {exc}" for ref, exc in self.errors]
        super().__init__("infra resolution failed: " + "; ".join(parts))


_LEAF_KINDS = {
    "Infrastructure",
    "LLMProxy",
    "LLMLocal",
    "InfraMiddleware",
    "InfraInterceptor",
    "ToolServerRegistry",
    "PersonalSecrets",
    "Application",
    "ToolRegistry",
    "ToolProvider",
    "SecretsProvider",
    "Datastore",
}
_VALID_KINDS = _LEAF_KINDS | {"InfraBundle"}


def resolve_infra_refs(
    refs: list[str],
    *,
    anchor: Path | None = None,
    workspace: WorkspaceConfig | None = None,
    user: UserConfig | None = None,
    interceptors: list[str] | None = None,
    mas_config: dict[str, Any] | None = None,
) -> ResolvedInfra:
    """Load and merge infra manifests; populate ``ResolvedInfra.llm_proxy``."""
    from mas.ctl.workspace.config import (
        collect_infra_interceptors,
        merge_infra_interceptors,
    )

    ws = workspace or WorkspaceConfig.load(anchor)
    usr = user or UserConfig.load()
    effective = list(refs)
    if not effective:
        if ws.effective_infra_refs:
            effective = list(ws.effective_infra_refs)
        elif usr.default_infra:
            effective = [usr.default_infra]
        else:
            effective = ["standard:production"]

    merged = InfraManifest(name="merged")
    errors: list[tuple[str, Exception]] = []
    for ref in effective:
        try:
            part = _load_ref(ref, anchor=anchor or Path.cwd(), workspace=ws)
            merged = _merge(merged, part)
        except Exception as exc:
            errors.append((ref, exc))

    mas_interceptors = collect_infra_interceptors(mas_config or {})
    merged_interceptors = merge_infra_interceptors(
        mas_interceptors=mas_interceptors,
        workspace_interceptors=list(ws.infra_interceptors),
        cli_interceptors=list(interceptors or []),
    )
    for ref in merged_interceptors:
        try:
            part = _load_ref(ref, anchor=anchor or Path.cwd(), workspace=ws)
            merged.pipeline = _merge_pipeline(merged.pipeline, part.pipeline)
        except Exception as exc:
            errors.append((ref, exc))

    if errors:
        for ref, exc in errors:
            logger.error("infra ref %r failed: %s", ref, exc)
        raise InfraResolveError(errors)

    llm = merged.to_llm_proxy_dict()
    cache_path = usr.cache_dir / "llm_cache.json"
    llm["cache_path"] = str(cache_path)
    llm["pipeline"] = _filter_pipeline_for_target(llm.get("pipeline") or [], "LLM_CALL")
    _hydrate_pipeline_cache_paths(llm.get("pipeline") or [], cache_path=cache_path)

    return ResolvedInfra(
        refs=effective,
        llm_proxy=llm,
        observability={},
    )


def bidirectional_pipeline_for(
    llm_proxy: dict[str, Any],
    *,
    handlers: dict[str, Any] | None = None,
) -> BidirectionalInfraPipeline:
    """Build a bidirectional infra chain from a resolved ``llm_proxy`` dict."""
    steps = list(llm_proxy.get("pipeline") or [])
    return BidirectionalInfraPipeline.from_pipeline_steps(steps, handlers=handlers)


def bidirectional_pipeline_for_infra(
    infra: ResolvedInfra,
    *,
    handlers: dict[str, Any] | None = None,
) -> BidirectionalInfraPipeline:
    """Convenience wrapper for :func:`bidirectional_pipeline_for`."""
    return bidirectional_pipeline_for(infra.llm_proxy, handlers=handlers)


def _load_ref(ref: str, *, anchor: Path, workspace: WorkspaceConfig) -> InfraManifest:
    if ref.startswith(("http://", "https://")):
        is_local = "localhost" in ref or "127.0.0.1" in ref
        return InfraManifest(
            name=f"inline:{ref}",
            kind="LLMLocal" if is_local else "LLMProxy",
            proxy=ProxySpec(api_base=ref),
        )

    path = _resolve_ref_path(ref, anchor=anchor, workspace=workspace)
    return _load_file(path, workspace=workspace)


def _resolve_ref_path(ref: str, *, anchor: Path, workspace: WorkspaceConfig) -> Path:
    if ":" in ref and "://" not in ref:
        lib_path = workspace.resolve_library_path(ref)
        if lib_path is not None:
            return lib_path
        bundle_path = _entry_point_bundle_path(ref)
        if bundle_path is not None:
            return bundle_path

    candidate = Path(ref).expanduser()
    if candidate.is_file():
        return candidate.resolve()

    return resolve_ref_with_search(
        ref,
        anchor,
        search_dirs=_infra_search_dirs(anchor, workspace),
    )


def _infra_search_dirs(anchor: Path, workspace: WorkspaceConfig) -> list[Path]:
    dirs: list[Path] = []
    if workspace.root:
        # Workspace refs like ``standard:openai`` resolve from workspace root.
        dirs.append(workspace.root)
        dirs.append(workspace.root / "infra")
        dirs.append(workspace.root / "config" / "infra")
    dirs.extend(
        [
            anchor,
            anchor.parent,
            mas_infra_dir(),
        ]
    )
    return dirs


def _entry_point_bundle_path(ref: str) -> Path | None:
    if ":" not in ref:
        return None
    lib_name, bundle_name = ref.split(":", 1)
    libs = list_manifest_libraries()
    pkg = libs.get(lib_name)
    if pkg:
        path = _bundle_path_in_package(pkg, lib_name, bundle_name)
        if path is not None:
            return path

    mas_lab = os.environ.get("MAS_LAB_ROOT")
    if mas_lab:
        rel = bundle_name.replace(":", "/")
        for root in (
            Path(mas_lab) / "library-standard" / "src" / "mas" / "library" / "standard" / "libs" / lib_name,
            Path(mas_lab) / "library-standard" / "libs" / lib_name,
        ):
            for candidate in (root / f"{rel}.yaml", root / rel / "bundle.yaml"):
                if candidate.is_file():
                    return candidate.resolve()
    return None


def _bundle_path_in_package(pkg: str, lib_name: str, bundle_name: str) -> Path | None:
    try:
        from importlib.resources import as_file, files

        rel = bundle_name.replace(":", "/")
        bundle_path = files(pkg) / "libs" / lib_name / f"{rel}.yaml"
        with as_file(bundle_path) as p:
            path = Path(p)
            if path.is_file():
                return path.resolve()
    except Exception:
        return None
    return None


def _load_file(
    path: Path,
    *,
    workspace: WorkspaceConfig,
    _seen: frozenset[Path] | None = None,
) -> InfraManifest:
    path = path.resolve()
    seen = (_seen or frozenset()) | {path}
    data = load_yaml_file(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    data = resolve_manifest_values(data)
    kind = data.get("kind", "")
    if kind not in _VALID_KINDS:
        raise ValueError(f"{path}: unsupported kind {kind!r}")

    if kind == "InfraBundle":
        parts: list[InfraManifest] = []
        spec = data.get("spec") or {}
        pipeline: list[dict[str, Any]] = []
        entries = spec.get("entries")
        if isinstance(entries, list) and entries:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                ref = entry.get("ref")
                if not ref:
                    continue
                child = _resolve_ref_path(str(ref), anchor=path.parent, workspace=workspace)
                if child in seen:
                    raise ValueError(f"circular InfraBundle reference: {path} -> {child}")
                parts.append(_load_file(child, workspace=workspace, _seen=seen))
                for step in entry.get("pipeline") or []:
                    pipeline.append(
                        _resolve_pipeline_entry(step, anchor=path.parent, workspace=workspace)
                    )
        else:
            for entry in spec.get("interceptors") or spec.get("pipeline") or []:
                pipeline.append(_resolve_pipeline_entry(entry, anchor=path.parent, workspace=workspace))
            for ref in spec.get("includes", []):
                child = _resolve_ref_path(str(ref), anchor=path.parent, workspace=workspace)
                if child in seen:
                    raise ValueError(f"circular InfraBundle reference: {path} -> {child}")
                parts.append(_load_file(child, workspace=workspace, _seen=seen))
        merged = _merge_many(parts)
        merged.pipeline = _merge_pipeline(merged.pipeline, pipeline)
        meta = data.get("metadata") or {}
        merged.name = meta.get("name", path.stem)
        merged.kind = "InfraBundle"
        return merged

    if kind in {"InfraMiddleware", "InfraInterceptor"}:
        spec = data.get("spec") or {}
        applies = spec.get("applies_to") or ["LLM_CALL"]
        if isinstance(applies, str):
            applies = [applies]
        return InfraManifest(
            name=str((data.get("metadata") or {}).get("name", path.stem)),
            kind=kind,
            pipeline=[
                {
                    "middleware": spec.get("middleware") or path.stem.replace("-", "_"),
                    "params": dict(spec.get("params") or {}),
                    "applies_to": list(applies),
                }
            ],
            raw=data,
        )

    return _from_dict(data)


def _from_dict(data: dict[str, Any]) -> InfraManifest:
    meta = data.get("metadata") or {}
    spec = data.get("spec") or {}
    kind = data.get("kind", "")
    proxy_raw = spec.get("proxy") or spec.get("server") or {}
    models_raw = spec.get("models") or {}
    defaults = models_raw.get("defaults") or spec.get("defaults") or {}
    if "api_key_env" in proxy_raw:
        api_key_env = str(proxy_raw.get("api_key_env") or "")
    else:
        api_key_env = "OPENAI_API_KEY"
    return InfraManifest(
        name=str(meta.get("name", "")),
        kind=kind,
        proxy=ProxySpec(
            api_base=str(proxy_raw.get("api_base", "") or ""),
            api_key_env=api_key_env,
        ),
        models=ModelsSpec(
            allowed=list(models_raw.get("allowed") or models_raw.get("available") or []),
            default_llm=defaults.get("llm"),
            default_embed=defaults.get("embed") or defaults.get("embedding"),
            mappings=dict(models_raw.get("mappings") or {}),
        ),
        model_access=dict(spec.get("model_access") or {}),
        raw=data,
    )


def _merge(a: InfraManifest, b: InfraManifest) -> InfraManifest:
    return _merge_many([a, b])


def _merge_many(parts: list[InfraManifest]) -> InfraManifest:
    if not parts:
        return InfraManifest(name="empty")
    proxy = ProxySpec()
    allowed: list[str] = []
    seen_allowed: set[str] = set()
    mappings: dict[str, str] = {}
    default_llm: str | None = None
    default_embed: str | None = None
    model_access: dict[str, Any] = {}
    pipeline: list[dict[str, Any]] = []
    name = parts[-1].name

    for m in parts:
        if m.proxy.api_base:
            proxy = ProxySpec(api_base=m.proxy.api_base, api_key_env=m.proxy.api_key_env)
        pipeline = _merge_pipeline(pipeline, m.pipeline)
        for item in m.models.allowed:
            if item not in seen_allowed:
                seen_allowed.add(item)
                allowed.append(item)
        mappings.update(m.models.mappings)
        if m.models.default_llm:
            default_llm = m.models.default_llm
        if m.models.default_embed:
            default_embed = m.models.default_embed
        model_access.update(m.model_access)

    return InfraManifest(
        name=name,
        kind="InfraBundle" if len(parts) > 1 else parts[0].kind,
        proxy=proxy,
        models=ModelsSpec(
            allowed=allowed,
            default_llm=default_llm,
            default_embed=default_embed,
            mappings=mappings,
        ),
        model_access=model_access,
        pipeline=pipeline,
    )


def _resolve_pipeline_entry(
    entry: Any,
    *,
    anchor: Path,
    workspace: WorkspaceConfig,
) -> dict[str, Any]:
    if isinstance(entry, str):
        child_path = _resolve_ref_path(entry, anchor=anchor, workspace=workspace)
        loaded = _load_file(child_path, workspace=workspace)
        if loaded.pipeline:
            return dict(loaded.pipeline[0])
        return {"middleware": entry.split(":")[-1].replace("-", "_"), "params": {}}
    if isinstance(entry, dict):
        if "ref" in entry:
            return _resolve_pipeline_entry(str(entry["ref"]), anchor=anchor, workspace=workspace)
        mid = entry.get("middleware") or entry.get("id")
        return {"middleware": mid, "params": dict(entry.get("params") or {})}
    raise ValueError(f"invalid pipeline entry: {entry!r}")


def _merge_pipeline(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(a) + list(b)


def _filter_pipeline_for_target(
    pipeline: list[dict[str, Any]], target: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in pipeline:
        applies = entry.get("applies_to") or ["LLM_CALL"]
        if isinstance(applies, str):
            applies = [applies]
        if target in applies:
            out.append(entry)
    return out


def _hydrate_pipeline_cache_paths(
    pipeline: list[dict[str, Any]], *, cache_path: Path
) -> None:
    for entry in pipeline:
        mid = str(entry.get("middleware") or "")
        if mid not in {"llm_cache", "llm-cache"}:
            continue
        params = entry.setdefault("params", {})
        if not params.get("cache_path"):
            params["cache_path"] = str(cache_path)


def api_key_for_infra(llm_proxy: dict[str, Any]) -> str:
    """Read secret from env var named by the infra manifest ``api_key_env`` field."""
    env_name = llm_proxy.get("api_key_env") or "OPENAI_API_KEY"
    return os.environ.get(str(env_name), "").strip()
