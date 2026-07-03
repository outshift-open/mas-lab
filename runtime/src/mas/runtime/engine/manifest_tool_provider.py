#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Load ``spec.tools[]`` entries into a manifest-scoped tool provider."""

from __future__ import annotations

import hashlib
import importlib.util as importlib_util
import inspect
import logging
import sys
import threading
import types
from pathlib import Path
from typing import Any

import yaml

from mas.runtime.contracts.tool_contract import ToolContract
from mas.runtime.manifest.schema import ToolDocument

logger = logging.getLogger(__name__)

# Parallel bench runs (e.g. parallel_scenarios > 1) materialize agents concurrently.
# Without a lock, two threads can race on sys.modules registration before exec_module
# finishes — producing "module has no attribute 'RunActionTool'" intermittently.
_TOOL_MODULE_LOAD_LOCK = threading.RLock()


class ManifestToolLoadError(RuntimeError):
    """Raised when a manifest tool entry cannot be loaded."""


def _containment_roots(
    manifest_dir: Path,
    app_root: Path | None,
    *,
    workspace_root: Path | None = None,
) -> tuple[Path, ...]:
    seen = {manifest_dir.resolve(): None}
    if app_root is not None:
        app = app_root.resolve()
        if workspace_root is not None:
            stop = workspace_root.resolve()
            for parent in (app, *app.parents):
                seen[parent.resolve()] = None
                if parent == stop:
                    break
        else:
            seen[app] = None
    from mas.library_roots import discover_library_roots

    for lib_root in discover_library_roots(manifest_dir, app_root):
        seen[lib_root.resolve()] = None
    return tuple(seen)


def _resolve_under_roots(
    ref_base: Path,
    ref: str,
    *,
    containment_roots: tuple[Path, ...],
) -> Path:
    """Resolve *ref* (relative, ``samples:…``, or ``pkg://``); must stay under a containment root."""
    if Path(ref).is_absolute():
        raise ManifestToolLoadError(f"absolute tool path not allowed: {ref!r}")

    from mas.runtime.package_refs import resolve_path_ref

    if ref.startswith("pkg://"):
        path = resolve_path_ref(ref, ref_base).resolve()
    elif ":" in ref and not ref.startswith(("/", "\\")):
        scheme, _, rel = ref.partition(":")
        if scheme and "/" not in scheme and "\\" not in scheme and rel:
            path = resolve_path_ref(ref, ref_base).resolve()
        else:
            path = (ref_base.resolve() / ref).resolve()
    else:
        path = (ref_base.resolve() / ref).resolve()

    for root in containment_roots:
        try:
            path.relative_to(root)
            return path
        except ValueError:
            continue
    raise ManifestToolLoadError(
        f"path escapes allowed roots: {ref!r} from {ref_base} "
        f"(roots: {', '.join(str(r) for r in containment_roots)})"
    )


def _tool_class_candidates(module: Any) -> list[type]:
    """Classes in *module* that expose tool collection (ToolContract or duck-typed)."""
    out: list[type] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ != module.__name__:
            continue
        if issubclass(obj, ToolContract) and obj is not ToolContract:
            out.append(obj)
            continue
        if callable(getattr(obj, "on_collect_tools", None)):
            out.append(obj)
    return out


class ManifestToolProvider:
    """Dispatch tool calls to ToolContract instances loaded from manifest refs."""

    def __init__(self) -> None:
        self._tool_instances: list[Any] = []
        self._tool_contracts: dict[str, dict[str, Any]] = {}

    def has_tools(self) -> bool:
        return bool(self._tool_instances)

    def list_tools(self) -> list[dict[str, Any]]:
        """Aggregate OpenAI-style tool specs from loaded instances."""
        result: list[dict[str, Any]] = []
        for instance in self._tool_instances:
            try:
                specs = instance.on_collect_tools()
                if specs:
                    for spec in specs:
                        merged = dict(spec)
                        yaml_contract = self._tool_contracts.get(str(spec.get("name")))
                        if yaml_contract:
                            merged["name"] = yaml_contract.get("name", merged.get("name"))
                            merged["description"] = yaml_contract.get(
                                "description", merged.get("description", "")
                            )
                            merged["parameters"] = yaml_contract.get(
                                "parameters", merged.get("parameters", {})
                            )
                        result.append(merged)
                    continue
            except NotImplementedError:
                pass
            except Exception:
                raise
            try:
                legacy = {
                    "name": instance.get_name(),
                    "description": instance.get_description(),
                    "parameters": instance.get_parameters_schema(),
                }
                yaml_contract = self._tool_contracts.get(str(legacy["name"]))
                if yaml_contract:
                    legacy.update(yaml_contract)
                result.append(legacy)
            except Exception as exc:
                raise ManifestToolLoadError(
                    f"Tool instance {instance!r} failed to describe itself: {exc}"
                ) from exc
        return result

    def list_openai_tools(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for spec in self.list_tools():
            name = str(spec.get("name") or "")
            if not name:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(spec.get("description") or f"Invoke tool {name}."),
                        "parameters": spec.get("parameters")
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        return out

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        user: str = "",
    ) -> Any:
        for instance in self._tool_instances:
            owns = False
            legacy_match = False
            try:
                specs = instance.on_collect_tools()
                owns = any(s.get("name") == tool_name for s in (specs or []))
            except NotImplementedError:
                pass
            except Exception:
                raise
            if not owns:
                try:
                    legacy_match = instance.get_name() == tool_name
                except Exception:
                    legacy_match = False
            if not owns and not legacy_match:
                continue
            try:
                result = instance.on_execute_tool(
                    tool_name, arguments, ctx=ctx, user=user
                )
                if result is not None:
                    return result
                if owns:
                    return ""
            except NotImplementedError:
                if legacy_match:
                    try:
                        return instance.execute(**arguments)
                    except NotImplementedError:
                        continue
                continue
            except Exception:
                raise
            if legacy_match:
                try:
                    return instance.execute(**arguments)
                except NotImplementedError:
                    continue
        raise ManifestToolLoadError(f"Tool {tool_name!r} not found in manifest provider")

    def _add_instance(
        self,
        instance: Any,
        manifest_contract: dict[str, Any] | None,
    ) -> None:
        if manifest_contract is not None:
            name = str(manifest_contract["name"])
            if name in self._tool_contracts:
                raise ManifestToolLoadError(
                    f"duplicate manifest tool name {name!r}"
                )
            self._tool_contracts[name] = manifest_contract
        self._tool_instances.append(instance)


def build_manifest_tool_provider(
    tools_spec: list[Any],
    manifest_dir: Path,
    *,
    app_root: Path | None = None,
    **containment_kw: Any,
) -> ManifestToolProvider:
    """Build a provider from ``spec.tools`` (refs or inline module_path entries)."""
    provider = ManifestToolProvider()
    if not tools_spec:
        return provider

    roots = _containment_roots(manifest_dir, app_root or manifest_dir, **containment_kw)
    for index, raw in enumerate(tools_spec):
        tool_def, mdir, manifest_contract = _normalize_tool_entry(
            raw, manifest_dir, index, containment_roots=roots
        )
        module_path = tool_def.get("module_path")
        if not module_path:
            raise ManifestToolLoadError(
                f"spec.tools[{index}]: missing module_path after resolving entry {raw!r}"
            )
        class_name = tool_def.get("class_name")
        params = dict(tool_def.get("params") or {})
        instance = _load_tool_instance(
            str(module_path),
            mdir,
            class_name=class_name,
            params=params,
            containment_roots=roots,
        )
        provider._add_instance(instance, manifest_contract)
    return provider


def _normalize_tool_entry(
    raw: Any,
    manifest_dir: Path,
    index: int,
    *,
    containment_roots: tuple[Path, ...],
) -> tuple[dict[str, Any], Path, dict[str, Any] | None]:
    if isinstance(raw, str):
        raise ManifestToolLoadError(
            f"spec.tools[{index}]: bare name {raw!r} is not supported; "
            "use {{ref: ./path/to/tool.tool.yaml}} or inline module_path"
        )
    if not isinstance(raw, dict):
        raise ManifestToolLoadError(f"spec.tools[{index}]: expected mapping, got {type(raw).__name__}")

    mdir = manifest_dir
    manifest_contract: dict[str, Any] | None = None
    tool_def = dict(raw)

    if tool_def.get("ref"):
        ref_path = _resolve_under_roots(
            mdir, str(tool_def["ref"]), containment_roots=containment_roots
        )
        if not ref_path.is_file():
            raise ManifestToolLoadError(f"spec.tools[{index}]: tool ref not found: {ref_path}")
        try:
            doc = yaml.safe_load(ref_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ManifestToolLoadError(f"spec.tools[{index}]: cannot read {ref_path}: {exc}") from exc
        if not isinstance(doc, dict):
            raise ManifestToolLoadError(f"spec.tools[{index}]: invalid tool YAML at {ref_path}")
        try:
            tool_contract = ToolDocument.from_dict(doc)
        except ValueError as exc:
            raise ManifestToolLoadError(f"spec.tools[{index}]: {exc}") from exc
        impl = (doc.get("spec") or {}).get("impl") or {}
        if not impl.get("module_path"):
            raise ManifestToolLoadError(
                f"spec.tools[{index}]: tool {ref_path} missing spec.impl.module_path"
            )
        tool_name = tool_contract.name or ref_path.stem.replace(".tool", "")
        manifest_contract = tool_contract.to_contract_dict(tool_name)
        tool_def = {
            "module_path": impl.get("module_path"),
            "class_name": impl.get("class_name"),
            "params": dict(impl.get("params") or {}),
        }
        mdir = ref_path.parent
    elif tool_def.get("module_path"):
        pass
    else:
        raise ManifestToolLoadError(
            f"spec.tools[{index}]: entry must include ref or module_path: {raw!r}"
        )

    return tool_def, mdir, manifest_contract


def _load_tool_instance(
    module_path: str,
    manifest_dir: Path,
    *,
    class_name: str | None,
    params: dict[str, Any],
    containment_roots: tuple[Path, ...],
) -> Any:
    is_file = (
        module_path.endswith(".py")
        or module_path.startswith((".", "/", "~"))
        or "/" in module_path
        or "\\" in module_path
    )
    if is_file:
        resolved = _resolve_under_roots(
            manifest_dir, module_path, containment_roots=containment_roots
        )
        if not resolved.is_file():
            raise ManifestToolLoadError(f"Tool module file not found: {resolved}")
        with _TOOL_MODULE_LOAD_LOCK:
            pkg_init = resolved.parent / "__init__.py"
            if pkg_init.exists():
                pkg_dir = resolved.parent
                pkg_hash = hashlib.sha1(str(pkg_dir).encode()).hexdigest()[:10]
                pkg_name = f"_mas_toolpkg_{pkg_dir.name}_{pkg_hash}"
                if pkg_name not in sys.modules:
                    pkg_mod = types.ModuleType(pkg_name)
                    pkg_mod.__path__ = [str(pkg_dir)]  # type: ignore[attr-defined]
                    pkg_mod.__package__ = pkg_name
                    sys.modules[pkg_name] = pkg_mod
                key = f"{pkg_name}.{resolved.stem}"
                package_name = pkg_name
            else:
                key = f"_mas_tool_{resolved}"
                package_name = None
            if key in sys.modules:
                module = sys.modules[key]
            else:
                spec = importlib_util.spec_from_file_location(key, resolved)
                if spec is None or spec.loader is None:
                    raise ManifestToolLoadError(f"Cannot load tool module: {resolved}")
                module = importlib_util.module_from_spec(spec)
                if package_name is not None:
                    module.__package__ = package_name
                sys.modules[key] = module
                spec.loader.exec_module(module)
    else:
        fromlist = [class_name] if class_name else [""]
        try:
            module = __import__(module_path, fromlist=fromlist)
        except ModuleNotFoundError:
            module = _import_bundled_module(module_path)

    if class_name:
        tool_class = getattr(module, class_name)
    else:
        candidates = _tool_class_candidates(module)
        if not candidates:
            raise ManifestToolLoadError(
                f"No tool class found in {module_path} "
                "(class_name required, or define on_collect_tools)."
            )
        if len(candidates) > 1:
            names = ", ".join(c.__name__ for c in candidates)
            raise ManifestToolLoadError(
                f"multiple tool classes in {module_path}: {names}; specify class_name"
            )
        tool_class = candidates[0]

    return tool_class(**params)


def _import_bundled_module(module_path: str) -> Any:
    """Resolve dotted module paths via importlib.resources when not on sys.path."""
    import importlib.resources as importlib_resources

    parts = module_path.split(".")
    if len(parts) < 2:
        raise ModuleNotFoundError(module_path)

    pkg_name = parts[0]
    sub_parts = parts[1:]

    try:
        pkg_root = importlib_resources.files(pkg_name)
    except (FileNotFoundError, ModuleNotFoundError, TypeError):
        raise ModuleNotFoundError(module_path) from None

    target = pkg_root
    for part in sub_parts[:-1]:
        target = target / part
    target = target / f"{sub_parts[-1]}.py"
    try:
        with importlib_resources.as_file(target) as resolved:
            if not resolved.is_file():
                raise ModuleNotFoundError(module_path)
            spec = importlib_util.spec_from_file_location(module_path, str(resolved))
            if spec is None or spec.loader is None:
                raise ModuleNotFoundError(f"Cannot load {resolved}")
            mod = importlib_util.module_from_spec(spec)
            sys.modules[module_path] = mod
            spec.loader.exec_module(mod)
            return mod
    except (FileNotFoundError, ModuleNotFoundError, TypeError):
        raise ModuleNotFoundError(module_path) from None


def attach_manifest_tools(
    engine: Any,
    manifest: dict | None,
    manifest_dir: Path | None,
    *,
    app_root: Path | None = None,
    **provider_kw: Any,
) -> ManifestToolProvider | None:
    """Load ``spec.tools`` and attach provider to the leaf engine."""
    from mas.runtime.engine.leaf import leaf_engine
    from mas.runtime.engine.llm_live import LiveLlmEngine
    from mas.runtime.engine.tools import tool_entry_name, tools_with_resolved_names

    spec = (manifest or {}).get("spec") or {}
    if manifest_dir is None and spec.get("tools"):
        raise ManifestToolLoadError("manifest_dir is required when spec.tools is non-empty")
    tools = (
        tools_with_resolved_names(list(spec.get("tools") or []), manifest_dir)
        if manifest_dir
        else list(spec.get("tools") or [])
    )
    if tools_remove := spec.get("tools_remove"):
        drop = {n for x in tools_remove if (n := tool_entry_name(x, base_dir=manifest_dir))}
        tools = [t for t in tools if not (n := tool_entry_name(t, base_dir=manifest_dir)) or n not in drop]
    if not tools:
        return None

    provider = build_manifest_tool_provider(
        tools, manifest_dir, app_root=app_root or manifest_dir, **provider_kw
    )
    leaf = leaf_engine(engine)
    leaf.tool_provider = provider
    if isinstance(leaf, LiveLlmEngine):
        leaf.manifest_dir = manifest_dir
    return provider


def attach_manifest_tools_to_instance(
    instance: Any,
    manifest: dict | None,
    manifest_dir: Path | None,
    *,
    app_root: Path | None = None,
    **provider_kw: Any,
) -> ManifestToolProvider | None:
    engine = getattr(getattr(instance, "driver", None), "engine", None)
    if engine is None:
        return None
    return attach_manifest_tools(
        engine, manifest, manifest_dir, app_root=app_root, **provider_kw
    )
