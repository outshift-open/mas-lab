#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Local tool-provider plugin — in-process Python ``spec.tools``.

Default ``kind: local`` binding from library-standard. The runtime registry
only maps names; this module loads ToolContract modules and executes them.
"""

from __future__ import annotations

import hashlib
import importlib.util as importlib_util
import inspect
import logging
import os
import sys
import threading
import types
from pathlib import Path
from typing import Any

import yaml
from mas.runtime.contracts.tool_contract import ToolContract, overlay_tool_advertise
from mas.runtime.contracts.user_communication_contract import HITLContract, UserIOContract
from mas.runtime.manifest.schema import ToolDocument
from mas.runtime.registry.provider_protocol import ManifestToolLoadError

logger = logging.getLogger(__name__)

_TOOL_MODULE_LOAD_LOCK = threading.RLock()


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
        f"path escapes allowed roots: {ref!r} from {ref_base} (roots: {', '.join(str(r) for r in containment_roots)})"
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


class LocalToolProvider:
    """In-process Python tools loaded from ``spec.tools``.

    Same plugin contract as MCP: ``discover_tools`` / ``list_tools`` / ``call_tool``.
    """

    origin = "local"
    kind = "local"

    def __init__(
        self,
        name: str = "in-process",
        tools_claim: str | list[str] | None = "*",
        *,
        implicit: bool = True,
    ) -> None:
        self.provider_name = name
        self.implicit = implicit
        if tools_claim is None or tools_claim == "*":
            self.tools_claim: str | tuple[str, ...] = "*"
        elif isinstance(tools_claim, str):
            self.tools_claim = (tools_claim,)
        else:
            self.tools_claim = tuple(str(n) for n in tools_claim)
        self._tool_instances: list[Any] = []
        self._tool_contracts: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_provider_spec(cls, spec: dict[str, Any]) -> "LocalToolProvider":
        """Bind an explicit ``kind: local`` ``spec.providers[]`` entry."""
        return cls(
            name=str(spec.get("name") or "in-process"),
            tools_claim=spec.get("tools", "*"),
            implicit=False,
        )

    def load_spec_tools(
        self,
        tools_spec: list[Any],
        manifest_dir: Path,
        **kwargs: Any,
    ) -> "LocalToolProvider":
        """Load ``spec.tools`` Python implementations into this provider."""
        return load_local_tool_provider(tools_spec, manifest_dir, provider=self, **kwargs)

    def has_tools(self) -> bool:
        return bool(self._tool_instances)

    def discover_tools(self, *, ctx: Any = None) -> list[dict[str, Any]]:
        return self.list_tools(ctx=ctx)

    def list_tools(self, *, ctx: Any = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for instance in self._tool_instances:
            try:
                specs = instance.on_collect_tools(ctx=ctx)
                if specs is not None:
                    for spec in specs:
                        yaml_contract = self._tool_contracts.get(str(spec.get("name")))
                        result.append(overlay_tool_advertise(spec, yaml_contract))
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
                raise ManifestToolLoadError(f"Tool instance {instance!r} failed to describe itself: {exc}") from exc
        return result

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        user: str = "",
        **kwargs: Any,
    ) -> Any:
        for instance in self._tool_instances:
            owns = False
            legacy_match = False
            try:
                specs = instance.on_collect_tools(ctx=ctx)
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
                result = instance.on_execute_tool(tool_name, arguments, ctx=ctx, user=user, **kwargs)
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
        raise ManifestToolLoadError(f"Tool {tool_name!r} not found in local provider")

    def _add_instance(
        self,
        instance: Any,
        manifest_contract: dict[str, Any] | None,
    ) -> None:
        if manifest_contract is not None:
            name = str(manifest_contract["name"])
            if name in self._tool_contracts:
                raise ManifestToolLoadError(f"duplicate manifest tool name {name!r}")
            self._tool_contracts[name] = manifest_contract
        self._tool_instances.append(instance)


class LocalToolClaim(LocalToolProvider):
    """Explicit ``kind: local`` overlay. Leftover names stay in-process."""

    def __init__(self, name: str = "in-process", tools_claim: str | list[str] | None = "*") -> None:
        super().__init__(name=name, tools_claim=tools_claim, implicit=False)


def load_local_tool_provider(
    tools_spec: list[Any],
    manifest_dir: Path,
    *,
    app_root: Path | None = None,
    include_system_tools: bool = True,
    hitl_contract: HITLContract | None = None,
    user_io_contract: UserIOContract | None = None,
    provider: LocalToolProvider | None = None,
    **containment_kw: Any,
) -> LocalToolProvider:
    """Load ``spec.tools`` Python implementations into the local plugin."""
    local = provider or LocalToolProvider()
    skills_spec = containment_kw.pop("skills_spec", None)
    auto_inject_scripts = bool(containment_kw.pop("auto_inject_scripts", False))
    containment_kw.pop("spec_behavior", None)

    if include_system_tools:
        hitl_params = _system_tool_params(tools_spec, "request_human_input")
        inform_user_params = _system_tool_params(tools_spec, "inform_user")
        _inject_system_tools(
            local,
            hitl_contract=hitl_contract,
            user_io_contract=user_io_contract,
            hitl_default_timeout_seconds=hitl_params.get("timeout"),
            hitl_auto_resolve_decision=hitl_params.get("auto_resolve_decision"),
            max_question_length=hitl_params.get("max_question_length"),
            max_message_length=inform_user_params.get("max_message_length"),
        )
        _inject_skill_system_tools(
            local,
            tools_spec=tools_spec,
            skills_spec=skills_spec,
            manifest_dir=manifest_dir,
            app_root=app_root,
            auto_inject_scripts=auto_inject_scripts,
        )

    if not tools_spec:
        return local

    roots = _containment_roots(manifest_dir, app_root or manifest_dir, **containment_kw)
    for index, raw in enumerate(tools_spec):
        if isinstance(raw, dict) and raw.get("kind") == "system":
            logger.debug(
                "spec.tools[%d]: skipping redundant system-tool declaration %r",
                index,
                raw.get("name"),
            )
            continue
        tool_def, mdir, manifest_contract = _normalize_tool_entry(raw, manifest_dir, index, containment_roots=roots)
        module_path = tool_def.get("module_path")
        if not module_path:
            raise ManifestToolLoadError(f"spec.tools[{index}]: missing module_path after resolving entry {raw!r}")
        class_name = tool_def.get("class_name")
        params = dict(tool_def.get("params") or {})
        instance = _load_tool_instance(
            str(module_path),
            mdir,
            class_name=class_name,
            params=params,
            containment_roots=roots,
        )
        local._add_instance(instance, manifest_contract)
    return local


def _system_tool_params(tools_spec: list[Any], name: str) -> dict[str, Any]:
    """Extract ``params`` from a ``{kind: system, name: <name>}`` entry in
    ``spec.tools``, if declared -- the manifest-level config for a system
    tool (e.g. request_human_input's timeout/auto_resolve_decision/
    max_question_length, or inform_user's max_message_length)."""
    for raw in tools_spec or []:
        if isinstance(raw, dict) and raw.get("kind") == "system" and raw.get("name") == name:
            return dict(raw.get("params") or {})
    return {}


def _inject_system_tools(
    provider: LocalToolProvider,
    *,
    hitl_contract: HITLContract | None = None,
    user_io_contract: UserIOContract | None = None,
    hitl_default_timeout_seconds: float | None = None,
    hitl_auto_resolve_decision: str | None = None,
    max_question_length: int | None = None,
    max_message_length: int | None = None,
) -> None:
    """Add built-in system tools to the provider.

    System tools are runtime-level capabilities exposed as tools:
    - request_human_input: blocking agent-initiated HITL
    - inform_user: non-blocking user progress updates
    """
    from mas.runtime.system_tools import InformUserTool, RequestHumanInputTool

    request_human_input_kwargs: dict[str, Any] = {}
    if max_question_length is not None:
        request_human_input_kwargs["max_question_length"] = int(max_question_length)
    inform_user_kwargs: dict[str, Any] = {}
    if max_message_length is not None:
        inform_user_kwargs["max_message_length"] = int(max_message_length)

    provider._add_instance(
        _SystemToolHitlWrapper(
            RequestHumanInputTool(**request_human_input_kwargs),
            hitl_contract=hitl_contract,
            default_timeout_seconds=hitl_default_timeout_seconds,
            auto_resolve_decision=hitl_auto_resolve_decision,
        ),
        manifest_contract=None,
    )
    provider._add_instance(
        _SystemToolUserUpdateWrapper(InformUserTool(**inform_user_kwargs), user_io_contract=user_io_contract),
        manifest_contract=None,
    )


def _inject_skill_system_tools(
    provider: LocalToolProvider,
    *,
    tools_spec: list[Any] | None,
    skills_spec: Any,
    manifest_dir: Path,
    app_root: Path | None,
    auto_inject_scripts: bool,
) -> None:
    """Optional skill system tools — no-op when mas-library-skills is absent."""
    try:
        from mas.library.skills.plugins.system_tools import inject_skill_system_tools
    except ImportError:
        return
    inject_skill_system_tools(
        provider,
        tools_spec=tools_spec,
        skills_spec=skills_spec,
        base_dir=app_root or manifest_dir,
        auto_inject_scripts=auto_inject_scripts,
    )


class _SystemToolWrapperBase:
    """Shared boilerplate for system-tool wrappers that catch a control-flow signal.

    `request_human_input` (blocking HITL) and `inform_user` (non-blocking status
    update) both wrap a plain `ToolContract` instance, forward tool collection
    and normal execution unchanged, and only diverge once their tool raises its
    own sentinel signal. That common plumbing lives here so the two wrappers
    only need to implement their signal-handling branch.
    """

    def __init__(self, tool_instance: Any) -> None:
        self._tool = tool_instance

    def on_collect_tools(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Forward tool collection to wrapped instance.

        Accepts and forwards arbitrary kwargs (e.g. ``ctx``) so a wrapped
        tool that needs runtime context to build its schema (see
        SkillToolsPlugin.on_collect_tools) still gets it through this
        wrapper -- LocalToolProvider.list_tools/call_tool always pass
        ``ctx=`` now.
        """
        if hasattr(self._tool, "on_collect_tools"):
            return self._tool.on_collect_tools(**kwargs)
        # Fallback to legacy API
        try:
            return [
                {
                    "name": self._tool.get_name(),
                    "description": self._tool.get_description(),
                    "parameters": self._tool.get_parameters_schema(),
                }
            ]
        except (AttributeError, NotImplementedError):
            return []

    def _execute_wrapped(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any,
        user: str,
    ) -> Any:
        """Run the wrapped tool's normal (non-signal) execution path."""
        return self._tool.execute(**arguments)

    @staticmethod
    def _extract_context(ctx: Any) -> tuple[str, str, int]:
        """Pull (session_id, agent_id, correlation_id) off the call context."""
        return (
            getattr(ctx, "session_id", "unknown"),
            getattr(ctx, "agent_id", "unknown"),
            getattr(ctx, "correlation_id", 0),
        )


class _SystemToolHitlWrapper(_SystemToolWrapperBase):
    """Wrapper for system tools that emit HITL signals.

    Catches RequestHitlSignal and resolves it, in priority order:
    1. Batch/CLI/bench mode (MAS_HITL_AUTO_RESOLVE set): auto-resolve immediately,
       no external resolver is listening.
    2. hitl_contract.request_approval() -- defaults to RegistryHitlContract
       (register in the shared HitlResolverRegistry and BLOCK until an external
       resolver, e.g. an external integration or an interactive CLI prompt, provides the
       user's response) unless a different HITLContract was supplied.

    Timeout handling (RegistryHitlContract path):
    - The call's own `timeout` argument wins; otherwise `default_timeout_seconds`
      (the manifest-configured default, if any) applies; with neither set, the
      wait has no timeout at all.
    - If a timeout is set and elapses before resolution → raises TimeoutError
    - No auto-approval (user must explicitly respond)
    """

    def __init__(
        self,
        tool_instance: Any,
        hitl_contract: HITLContract | None = None,
        *,
        default_timeout_seconds: float | None = None,
        auto_resolve_decision: str | None = None,
    ) -> None:
        super().__init__(tool_instance)
        if hitl_contract is None:
            from mas.runtime.contracts.user_communication_contract import RegistryHitlContract

            hitl_contract = RegistryHitlContract()
        self._hitl_contract: HITLContract = hitl_contract
        self._default_timeout_seconds = default_timeout_seconds
        self._auto_resolve_decision = (
            auto_resolve_decision or os.environ.get("MAS_HITL_AUTO_RESOLVE_DECISION") or "approve"
        )

    def on_execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        user: str = "",
    ) -> Any:
        """Execute tool and catch HITL signal.

        If the tool raises RequestHitlSignal, resolve it via auto-resolve or
        self._hitl_contract.request_approval() (in that order).
        """
        from mas.runtime.system_tools.signal import RequestHitlSignal

        try:
            return self._execute_wrapped(tool_name, arguments, ctx=ctx, user=user)
        except RequestHitlSignal as signal:
            session_id, agent_id, correlation_id = self._extract_context(ctx)

            # Batch/CLI auto-hitl mode (e.g. `mas-ctl run-mas --auto-hitl`, the
            # default): there is no external resolver (integration adapter, operator
            # console, etc.) listening on the registry, so blocking for the
            # full timeout would always fail. Resolve immediately with a
            # default choice instead, mirroring the existing AutoApproveResponder
            # semantics used for the older governance-triggered HITL path.
            # Real interactive/production sessions never set this env var, so
            # they keep blocking for an actual external resolver as before.
            if os.environ.get("MAS_HITL_AUTO_RESOLVE", "0") not in ("0", "false", "False", ""):
                logger.info(
                    f"Agent {agent_id} HITL auto-resolved in batch mode "
                    f"(session={session_id}, correlation_id={correlation_id}): "
                    f"question={signal.question!r} choice={self._auto_resolve_decision!r}"
                )
                return {"choice": self._auto_resolve_decision, "steering": ""}

            timeout_seconds = signal.timeout if signal.timeout is not None else self._default_timeout_seconds
            logger.info(
                f"Agent {agent_id} awaiting HITL resolution "
                f"(timeout={timeout_seconds if timeout_seconds is not None else 'none'}s): "
                f"{signal.question}"
            )
            result = self._hitl_contract.request_approval(
                question=signal.question,
                session_id=session_id,
                requesting_user_id=user,
                agent_id=agent_id,
                correlation_id=correlation_id,
                question_type=signal.question_type.value,
                choices=signal.choices,
                context_data=signal.context_data,
                timeout=timeout_seconds,
            )
            logger.info("Agent %s HITL resolved: user chose '%s'", agent_id, result.get("choice"))
            return result


class _SystemToolUserUpdateWrapper(_SystemToolWrapperBase):
    """Wrapper for system tools that emit non-blocking user status updates.

    Catches InformUserSignal and routes it through
    user_io_contract.send_progress_update() -- defaults to RegistryUserIOContract
    (register in the shared HitlResolverRegistry's user-update channel, e.g.
    polled by an external integration) unless a different UserIOContract was supplied.

    Unlike `_SystemToolHitlWrapper`, this never blocks: the tool call returns
    immediately regardless of which implementation consumes the update.
    """

    def __init__(self, tool_instance: Any, user_io_contract: UserIOContract | None = None) -> None:
        super().__init__(tool_instance)
        if user_io_contract is None:
            from mas.runtime.contracts.user_communication_contract import (
                RegistryUserIOContract,
            )

            user_io_contract = RegistryUserIOContract()
        self._user_io_contract: UserIOContract = user_io_contract

    def on_execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        ctx: Any = None,
        user: str = "",
    ) -> Any:
        """Execute tool and catch the non-blocking update signal."""
        from mas.runtime.system_tools.signal import InformUserSignal

        try:
            return self._execute_wrapped(tool_name, arguments, ctx=ctx, user=user)
        except InformUserSignal as signal:
            session_id, agent_id, correlation_id = self._extract_context(ctx)

            receipt = self._user_io_contract.send_progress_update(
                message=signal.message,
                session_id=session_id,
                requesting_user_id=signal.user_name or user,
                agent_id=agent_id,
                correlation_id=correlation_id,
                involved_agents=signal.involved_agents,
                metadata=signal.metadata,
            )
            logger.info(
                "Agent %s sent progress update for session=%s: %s",
                agent_id,
                session_id,
                signal.message,
            )
            return {
                "status": "sent",
                "message": signal.message,
                "user_name": signal.user_name or user,
                "involved_agents": list(signal.involved_agents),
                "metadata": dict(signal.metadata),
                "blocking": False,
                "receipt": receipt,
            }


def _normalize_tool_entry(
    raw: Any,
    manifest_dir: Path,
    index: int,
    *,
    containment_roots: tuple[Path, ...],
) -> tuple[dict[str, Any], Path, dict[str, Any] | None]:
    catalog_ref_path: Path | None = None
    raw_entry_params: dict[str, Any] = {}
    if isinstance(raw, str):
        from mas.library_catalog import find_tool_manifest

        catalog_ref_path = find_tool_manifest(raw)
        if catalog_ref_path is None:
            raise ManifestToolLoadError(
                f"spec.tools[{index}]: tool name {raw!r} not found in any library "
                f"catalog (library.yaml tools:, tools/{raw}.tool.yaml, or "
                f"tools/{raw}/*.tool.yaml). Declare it in a library, or use "
                "{{ref: ./path.tool.yaml}} / inline module_path."
            )
        tool_def: dict[str, Any] = {}
    elif not isinstance(raw, dict):
        raise ManifestToolLoadError(f"spec.tools[{index}]: expected mapping, got {type(raw).__name__}")
    else:
        tool_def = dict(raw)
        raw_entry_params = dict(tool_def.get("params") or {})

    mdir = manifest_dir
    manifest_contract: dict[str, Any] | None = None

    if catalog_ref_path is not None or tool_def.get("ref"):
        # A bare name resolves through the trusted library tool catalog (the
        # infra name→implementation mapping) and is not subject to manifest
        # containment; an explicit {ref: ...} is resolved under the manifest's
        # containment roots.
        if catalog_ref_path is not None:
            ref_path = catalog_ref_path
        else:
            ref_path = _resolve_under_roots(mdir, str(tool_def["ref"]), containment_roots=containment_roots)
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
            raise ManifestToolLoadError(f"spec.tools[{index}]: tool {ref_path} missing spec.impl.module_path")
        tool_name = tool_contract.name or ref_path.stem.replace(".tool", "")
        manifest_contract = tool_contract.to_contract_dict(tool_name)
        tool_def = {
            "module_path": impl.get("module_path"),
            "class_name": impl.get("class_name"),
            "params": dict(impl.get("params") or {}),
        }
        if raw_entry_params:
            merged_params = dict(tool_def["params"])
            merged_params.update(raw_entry_params)
            tool_def["params"] = merged_params
        mdir = ref_path.parent
    elif tool_def.get("module_path"):
        pass
    else:
        raise ManifestToolLoadError(f"spec.tools[{index}]: entry must include ref or module_path: {raw!r}")

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
        resolved = _resolve_under_roots(manifest_dir, module_path, containment_roots=containment_roots)
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
                f"No tool class found in {module_path} (class_name required, or define on_collect_tools)."
            )
        if len(candidates) > 1:
            names = ", ".join(c.__name__ for c in candidates)
            raise ManifestToolLoadError(f"multiple tool classes in {module_path}: {names}; specify class_name")
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
