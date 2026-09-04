#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Load ``spec.tools[]`` entries into a manifest-scoped tool provider."""

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

    def list_tools(self, *, ctx: Any = None) -> list[dict[str, Any]]:
        """Aggregate OpenAI-style tool specs from loaded instances.

        ``ctx`` is forwarded to each instance's ``on_collect_tools(ctx=ctx)``
        so a tool whose valid-argument set is only known at runtime (e.g.
        SkillToolsPlugin's activate_skill, constrained to ctx.skill_registry's
        actual names) can build an accurate schema instead of an unconstrained
        one -- real validation at the LLM API boundary, not a downstream
        fallback for names the schema should have rejected in the first place.
        """
        result: list[dict[str, Any]] = []
        for instance in self._tool_instances:
            try:
                specs = instance.on_collect_tools(ctx=ctx)
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

    def list_openai_tools(self, *, ctx: Any = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for spec in self.list_tools(ctx=ctx):
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
    include_system_tools: bool = True,
    hitl_contract: Any | None = None,
    user_io_contract: Any | None = None,
    **containment_kw: Any,
) -> ManifestToolProvider:
    """Build a provider from ``spec.tools`` (refs or inline module_path entries)."""
    provider = ManifestToolProvider()

    # Inject system tools first (always available, not in manifest). A
    # {kind: system, name: request_human_input, params: {...}} entry in
    # tools_spec configures the HITL wrapper (timeout, auto_resolve_decision)
    # even though it's otherwise a redundant/documentation-only declaration
    # (skipped below) — read it before injecting.
    if include_system_tools:
        hitl_params = _hitl_system_tool_params(tools_spec)
        _inject_system_tools(
            provider,
            hitl_contract=hitl_contract,
            user_io_contract=user_io_contract,
            hitl_default_timeout_seconds=hitl_params.get("timeout"),
            hitl_auto_resolve_decision=hitl_params.get("auto_resolve_decision"),
        )

    if not tools_spec:
        return provider

    roots = _containment_roots(manifest_dir, app_root or manifest_dir, **containment_kw)
    for index, raw in enumerate(tools_spec):
        if isinstance(raw, dict) and raw.get("kind") == "system":
            # System tools (request_human_input, inform_user) are always
            # auto-injected above via _inject_system_tools; an explicit
            # spec.tools entry for one is redundant declaration/documentation,
            # not a loadable ref/module_path entry — skip it rather than
            # raising ManifestToolLoadError. Its params (if any) were already
            # read above.
            logger.debug(
                "spec.tools[%d]: skipping redundant system-tool declaration %r",
                index,
                raw.get("name"),
            )
            continue
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


def _hitl_system_tool_params(tools_spec: list[Any]) -> dict[str, Any]:
    """Extract ``params`` from a ``{kind: system, name: request_human_input}``
    entry in ``spec.tools``, if declared -- the manifest-level default for
    the HITL wrapper's timeout/auto_resolve_decision (a call's own ``timeout``
    argument still wins over this)."""
    for raw in tools_spec or []:
        if (
            isinstance(raw, dict)
            and raw.get("kind") == "system"
            and raw.get("name") == "request_human_input"
        ):
            return dict(raw.get("params") or {})
    return {}


def _inject_system_tools(
    provider: ManifestToolProvider,
    *,
    hitl_contract: Any | None = None,
    user_io_contract: Any | None = None,
    hitl_default_timeout_seconds: float | None = None,
    hitl_auto_resolve_decision: str | None = None,
) -> None:
    """Add built-in system tools to the provider.

    System tools are runtime-level capabilities exposed as tools:
    - request_human_input: blocking agent-initiated HITL
    - inform_user: non-blocking user progress updates
    """
    from mas.runtime.system_tools import InformUserTool, RequestHumanInputTool

    provider._add_instance(
        _SystemToolHitlWrapper(
            RequestHumanInputTool(),
            hitl_contract=hitl_contract,
            default_timeout_seconds=hitl_default_timeout_seconds,
            auto_resolve_decision=hitl_auto_resolve_decision,
        ),
        manifest_contract=None,
    )
    provider._add_instance(
        _SystemToolUserUpdateWrapper(InformUserTool(), user_io_contract=user_io_contract),
        manifest_contract=None,
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
        wrapper -- ManifestToolProvider.list_tools/call_tool always pass
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
        if hasattr(self._tool, "on_execute_tool"):
            result = self._tool.on_execute_tool(tool_name, arguments, ctx=ctx, user=user)
            if result is not None:
                return result
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
    2. HITLContract, if one was supplied (e.g. an admin-approval abstraction).
    3. Fallback: register in the shared HitlResolverRegistry and BLOCK until an
       external resolver (e.g. the Webex bot) provides the user's response.

    Timeout handling (fallback path only):
    - The call's own `timeout` argument wins; otherwise `default_timeout_seconds`
      (the manifest-configured default, if any) applies; with neither set, the
      wait has no timeout at all.
    - If a timeout is set and elapses before resolution → raises TimeoutError
    - No auto-approval (user must explicitly respond)
    """

    def __init__(
        self,
        tool_instance: Any,
        hitl_contract: Any | None = None,
        *,
        default_timeout_seconds: float | None = None,
        auto_resolve_decision: str | None = None,
    ) -> None:
        super().__init__(tool_instance)
        self._hitl_contract = hitl_contract
        self._default_timeout_seconds = default_timeout_seconds
        self._auto_resolve_decision = (
            auto_resolve_decision
            or os.environ.get("MAS_HITL_AUTO_RESOLVE_DECISION")
            or "approve"
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
        
        If the tool raises RequestHitlSignal, resolve it via auto-resolve,
        HITLContract, or the registry-based blocking fallback (in that order).
        """
        from mas.runtime.system_tools.signal import RequestHitlSignal
        
        try:
            return self._execute_wrapped(tool_name, arguments, ctx=ctx, user=user)
        except RequestHitlSignal as signal:
            session_id, agent_id, correlation_id = self._extract_context(ctx)

            # Batch/CLI auto-hitl mode (e.g. `mas-ctl run-mas --auto-hitl`, the
            # default): there is no external resolver (Webex bot, operator
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

            # Route through HITLContract if available (e.g. an admin-approval
            # abstraction distinct from the raw Webex-bot registry channel).
            if self._hitl_contract is not None:
                try:
                    result = self._hitl_contract.request_approval(
                        question=signal.question,
                        session_id=session_id,
                        requesting_user_id=user,
                        agent_id=agent_id,
                        correlation_id=correlation_id,
                        question_type=signal.question_type.value,
                        choices=signal.choices,
                        context_data=signal.context_data,
                    )
                    logger.info(
                        "Agent %s HITL resolved via HITLContract: approver chose '%s'",
                        agent_id,
                        result.get("choice"),
                    )
                    return result
                except Exception as exc:
                    logger.warning(
                        "HITLContract approval failed for agent=%s session=%s: %s. "
                        "Falling back to registry.",
                        agent_id,
                        session_id,
                        exc,
                    )

            # Fallback: registry-based blocking resolution (production path —
            # e.g. the Webex bot resolves via resolve_agent_hitl()).
            resolution_event = threading.Event()
            resolution_result = {"choice": None, "steering": None}
            
            def callback(choice: str, steering: str) -> dict[str, str]:
                """Callback invoked by external resolver (Webex bot)."""
                resolution_result["choice"] = choice
                resolution_result["steering"] = steering
                resolution_event.set()  # Unblock waiting thread
                return {"status": "resolved", "choice": choice}
            
            from mas.runtime.boundary.hitl.registry import get_hitl_resolver_registry
            
            registry = get_hitl_resolver_registry()
            registry.register(
                session_id=session_id,
                agent_id=agent_id,
                correlation_id=correlation_id,
                question=signal.question,
                question_type=signal.question_type,
                choices=signal.choices,
                context_data=signal.context_data,
                resolver_callback=callback,  # ← This unblocks the agent
            )
            
            timeout_seconds = (
                signal.timeout if signal.timeout is not None else self._default_timeout_seconds
            )
            logger.info(
                f"Agent {agent_id} blocked waiting for HITL resolution "
                f"(timeout={timeout_seconds if timeout_seconds is not None else 'none'}s): "
                f"{signal.question}"
            )
            did_resolve = resolution_event.wait(timeout=timeout_seconds)

            if not did_resolve:
                # Timeout - no response from user. Clean up registry entry.
                try:
                    registry.resolve(
                        session_id, agent_id, correlation_id,
                        choice="__timeout__", steering="timeout"
                    )
                except KeyError:
                    pass  # Already resolved or cleaned up
                
                raise TimeoutError(
                    f"HITL request timed out after {timeout_seconds}s "
                    f"(session={session_id}, agent={agent_id}, "
                    f"correlation_id={correlation_id}): {signal.question}"
                )
            
            user_choice = resolution_result["choice"]
            user_steering = resolution_result["steering"] or ""
            
            logger.info(
                f"Agent {agent_id} HITL resolved: user chose '{user_choice}'"
            )
            
            return {
                "choice": user_choice,
                "steering": user_steering,
                "question": signal.question,
                "resolved": True,
            }


class _SystemToolUserUpdateWrapper(_SystemToolWrapperBase):
    """Wrapper for system tools that emit non-blocking user status updates.

    Catches InformUserSignal and routes it, in priority order:
    1. UserIOContract, if one was supplied.
    2. Fallback: register in the shared HitlResolverRegistry's user-update
       channel, polled by external systems (e.g. the Webex bot).

    Unlike `_SystemToolHitlWrapper`, this never blocks: the tool call returns
    immediately regardless of which channel consumes the update.
    """

    def __init__(self, tool_instance: Any, user_io_contract: Any | None = None) -> None:
        super().__init__(tool_instance)
        self._user_io_contract = user_io_contract

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

            # Route through UserIOContract if available.
            if self._user_io_contract is not None:
                try:
                    receipt = self._user_io_contract.send_progress_update(
                        message=signal.message,
                        session_id=session_id,
                        requesting_user_id=signal.user_name or user,
                        agent_id=agent_id,
                        involved_agents=signal.involved_agents,
                        metadata=signal.metadata,
                    )
                    logger.info(
                        "Agent %s sent progress update via UserIOContract for session=%s",
                        agent_id,
                        session_id,
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
                except Exception as exc:
                    logger.warning(
                        "UserIOContract progress update failed for agent=%s session=%s: %s. "
                        "Falling back to registry.",
                        agent_id,
                        session_id,
                        exc,
                    )

            # Fallback: direct registry registration (e.g. the Webex bot polls
            # get_pending_user_updates_for_session()).
            from mas.runtime.boundary.hitl.registry import get_hitl_resolver_registry

            registry = get_hitl_resolver_registry()
            registry.register_user_update(
                session_id=session_id,
                agent_id=agent_id,
                correlation_id=correlation_id,
                message=signal.message,
                user_name=signal.user_name or user,
                involved_agents=signal.involved_agents,
                metadata=signal.metadata,
            )

            logger.info(
                "Agent %s emitted non-blocking user update (registry fallback) for session=%s: %s",
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
        if raw_entry_params:
            merged_params = dict(tool_def["params"])
            merged_params.update(raw_entry_params)
            tool_def["params"] = merged_params
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
    from mas.runtime.engine.tools import tools_with_resolved_names

    spec = (manifest or {}).get("spec") or {}
    if manifest_dir is None and spec.get("tools"):
        raise ManifestToolLoadError("manifest_dir is required when spec.tools is non-empty")
    tools = (
        tools_with_resolved_names(list(spec.get("tools") or []), manifest_dir)
        if manifest_dir
        else list(spec.get("tools") or [])
    )
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
