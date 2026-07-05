#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Runtime observability plugin loader — binding → plugin instances.

This module is the runtime-side counterpart to the legacy ctl factory.
It reads an :class:`ObservabilityBinding` (a plain frozen dataclass) and
instantiates the declared export plugins using a simple lazy-import registry.
No ctl-specific types or if-chains in ctl; all plugin construction lives here.
"""

from __future__ import annotations

import importlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from mas.runtime.boundary.obs.binding import ObservabilityBinding
from mas.runtime.boundary.obs.observability_plugin import ObservabilityPlugin
from mas.runtime.boundary.obs.operator import ObservabilityOperator

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-import registry — maps plugin short-name to "module::ClassName".
# Keeps the door open to plugging into the real PluginRegistry later.
# ---------------------------------------------------------------------------

_OBS_LOADERS: dict[str, str] = {
    "native": "mas.library.standard.plugins.observability.native_plugin::NativeObservabilityPlugin",
    "otel": "mas.library.standard.plugins.observability.otel_plugin::OtelObservabilityPlugin",
    "ioa_observe": "mas.library.standard.plugins.observability.ioa_observe_plugin::IoaObservePlugin",
    "ioa-observe": "mas.library.standard.plugins.observability.ioa_observe_plugin::IoaObservePlugin",
    "observe_sdk": "mas.library.standard.plugins.observability.ioa_observe_plugin::IoaObservePlugin",
}

_DEFAULT_OTLP_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
_DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"


def _lazy_load_class(dotted_path: str) -> type:
    """Load a class from ``"module::ClassName"`` string."""
    module_path, class_name = dotted_path.split("::")
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def _resolve_events_path(base_dir: Path, binding: ObservabilityBinding) -> Path:
    if binding.events_file:
        p = Path(binding.events_file)
        return p if p.is_absolute() else (base_dir / p).resolve()
    return (base_dir / "traces" / "events.jsonl").resolve()


def _resolve_otlp_endpoint(binding: ObservabilityBinding, plugin_cfg: dict) -> str | None:
    env_name = str(
        plugin_cfg.get("otlp_endpoint_env")
        or binding.otlp_endpoint_env
        or _DEFAULT_OTLP_ENDPOINT_ENV
    )
    endpoint = os.environ.get(env_name, "").strip()
    if endpoint:
        return endpoint
    has_file = bool(
        plugin_cfg.get("output_path")
        or plugin_cfg.get("otel_file")
        or plugin_cfg.get("file_export_path")
        or plugin_cfg.get("path")
    )
    if has_file:
        return None
    return _DEFAULT_OTLP_ENDPOINT


def _build_native_plugin(
    binding: ObservabilityBinding,
    *,
    base_dir: Path,
    agent_id: str,
) -> ObservabilityPlugin:
    from mas.library.standard.lib.observability.emit import JsonlFileEmitter, StdoutJsonlEmitter
    from mas.library.standard.lib.observability.native.transform import (
        NativeObservabilityTransform,
        TransformContext,
    )
    from mas.library.standard.plugins.observability.native_plugin import NativeObservabilityPlugin

    native_cfg = binding.plugin_configs.get("native") or {}
    events_path = _resolve_events_path(base_dir, binding)
    if native_cfg.get("path"):
        p = Path(str(native_cfg["path"]))
        events_path = p if p.is_absolute() else (base_dir / p).resolve()

    emitters = []
    if binding.stdout:
        emitters.append(StdoutJsonlEmitter())
    emitters.insert(0, JsonlFileEmitter(events_path))

    ctx = TransformContext(
        agent_id=agent_id,
        run_id=os.environ.get("UI_RUN_ID", ""),
    )
    return NativeObservabilityPlugin(
        transforms=[NativeObservabilityTransform()],
        emitters=emitters,
        context=ctx,
    )


def _build_otel_plugin(
    binding: ObservabilityBinding,
    *,
    base_dir: Path,
    agent_id: str,
) -> ObservabilityPlugin | None:
    otel_cfg = binding.plugin_configs.get("otel") or {}
    try:
        from mas.library.standard.plugins.observability.otel_plugin import create_otel_plugin
    except (ImportError, RuntimeError):
        _logger.debug("otel plugin not available (library-standard[otel] not installed?)")
        return None

    from mas.library.standard.lib.observability.export_layers import parse_export_layers
    from mas.library.standard.lib.observability.native.transform import TransformContext

    events_path = _resolve_events_path(base_dir, binding)
    out = otel_cfg.get("output_path") or otel_cfg.get("otel_file")
    if out:
        out_path = Path(str(out))
        spans_path_str = (
            str(out_path)
            if out_path.suffix == ".jsonl"
            else str(out_path / "otel_sdk_spans.jsonl")
        )
    else:
        spans_path_str = str(events_path.parent / "otel_sdk_spans.jsonl")

    spans_path = Path(spans_path_str)
    if not spans_path.is_absolute():
        spans_path = (base_dir / spans_path).resolve()

    endpoint = _resolve_otlp_endpoint(binding, otel_cfg)
    if endpoint == _DEFAULT_OTLP_ENDPOINT and spans_path:
        endpoint = None

    service_name = str(otel_cfg.get("service_name") or agent_id or "mas-runtime")
    app_name = str(otel_cfg.get("app_name") or service_name)

    ctx = TransformContext(
        agent_id=agent_id,
        run_id=os.environ.get("UI_RUN_ID", ""),
    )
    return create_otel_plugin(
        spans_path=spans_path,
        context=ctx,
        mas_id="",
        service_name=service_name,
        app_name=app_name,
        otlp_endpoint=endpoint,
        export_layers=parse_export_layers(otel_cfg),
    )


def _build_ioa_observe_plugin(
    binding: ObservabilityBinding,
    *,
    base_dir: Path,
    agent_id: str,
) -> ObservabilityPlugin | None:
    ioa_cfg = (
        binding.plugin_configs.get("ioa_observe")
        or binding.plugin_configs.get("observe_sdk")
        or {}
    )
    try:
        from mas.library.ioa.ioa_observe import ObserveSDKPlugin
    except ImportError:
        _logger.debug("ioa_observe plugin not available")
        return None

    endpoint = _resolve_otlp_endpoint(binding, ioa_cfg)
    file_path = ioa_cfg.get("output_path") or ioa_cfg.get("file_export_path")
    if not file_path:
        events_path = _resolve_events_path(base_dir, binding)
        file_path = str(events_path.parent / "observe_sdk_spans.jsonl")
    if file_path and not Path(str(file_path)).is_absolute():
        file_path = str((base_dir / str(file_path)).resolve())

    service_name = str(
        ioa_cfg.get("service_name")
        or ioa_cfg.get("app_name")
        or agent_id
    )
    return ObserveSDKPlugin(
        app_name=service_name,
        is_entry_agent=bool(ioa_cfg.get("is_entry_agent", False)),
        endpoint=endpoint,
        file_export_path=file_path,
        trace_content=bool(ioa_cfg.get("trace_content", binding.trace_content)),
    )


def load_obs_plugins(
    binding: ObservabilityBinding,
    *,
    base_dir: Path,
    agent_id: str | None = None,
) -> list[ObservabilityPlugin]:
    """Instantiate observability plugins declared in *binding*.

    Uses a simple lazy-import registry (_OBS_LOADERS) for known plugin types.
    Unknown names fall back to importlib resolution if they look like a dotted
    module path; otherwise they are skipped with a warning.
    """
    resolved_agent_id = agent_id or "agent"
    if not binding.plugins:
        # Default to native when binding exists but no explicit plugin list.
        return [_build_native_plugin(binding, base_dir=base_dir, agent_id=resolved_agent_id)]

    plugins: list[ObservabilityPlugin] = []
    for name in binding.plugins:
        key = name.split("@")[0].strip()
        if key in ("native",):
            plugins.append(_build_native_plugin(binding, base_dir=base_dir, agent_id=resolved_agent_id))
        elif key in ("otel",):
            p = _build_otel_plugin(binding, base_dir=base_dir, agent_id=resolved_agent_id)
            if p is not None:
                plugins.append(p)
        elif key in ("ioa_observe", "ioa-observe", "observe_sdk"):
            p = _build_ioa_observe_plugin(binding, base_dir=base_dir, agent_id=resolved_agent_id)
            if p is not None:
                plugins.append(p)
        else:
            _logger.warning("unknown observability plugin %r — skipping", name)

    if not plugins:
        _logger.debug("no obs plugins built; falling back to native")
        plugins.append(_build_native_plugin(binding, base_dir=base_dir, agent_id=resolved_agent_id))

    return plugins


# ---------------------------------------------------------------------------
# ObsPluginSet — lifecycle wrapper around a list of plugins
# ---------------------------------------------------------------------------


@dataclass
class ObsPluginSet:
    """Lifecycle wrapper for a set of instantiated observability plugins.

    Returned by :func:`load_obs_plugins` wrapped here, and stored on
    :class:`~mas.runtime.driver.instance.RuntimeInstance` as ``obs_plugin_set``.
    """

    plugins: list[ObservabilityPlugin] = field(default_factory=list)
    # _operator: entry-agent operator — used for begin_run/end_run session events.
    # _all_operators: every operator that has plugins subscribed — drained on flush/close.
    # In single-agent runs _all_operators has exactly one entry.
    # In multi-agent (shared) runs _all_operators accumulates one entry per agent.
    _operator: ObservabilityOperator | None = field(default=None, init=False, repr=False)
    _all_operators: list = field(default_factory=list, init=False, repr=False)
    _mas_call_id: str = field(default="", init=False, repr=False)
    _run_started: bool = field(default=False, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def subscribe_to(
        self,
        op: ObservabilityOperator,
        *,
        agent_id: str,
        run_id: str = "",
    ) -> None:
        """Subscribe all plugins to *op* and set context.

        Idempotent: calling with the same *op* a second time is a no-op so that
        callers do not need to guard against redundant wiring.
        """
        if op in self._all_operators:
            return
        for plugin in self.plugins:
            op.subscribe(plugin)
        op.enable_async_plugins()
        op.set_context(agent_id=agent_id, run_id=run_id or os.environ.get("UI_RUN_ID", ""))
        self._all_operators.append(op)
        if self._operator is None:
            self._operator = op

    def begin_run(self, op: ObservabilityOperator) -> None:
        """Record mas_call_start transition."""
        if self._run_started:
            return
        self._run_started = True
        self._operator = op
        if op not in self._all_operators:
            self._all_operators.append(op)
        self._mas_call_id = str(uuid.uuid4())
        op.push_call_frame(self._mas_call_id)
        op.record_session("mas_call_start", call_id=self._mas_call_id)

    def end_run(self) -> None:
        """Record mas_call_end transition."""
        op = self._operator
        if op is None or not self._mas_call_id:
            return
        op.record_session("mas_call_end", call_id=self._mas_call_id, status="success")
        op.pop_call_frame(self._mas_call_id)
        self._mas_call_id = ""
        self._run_started = False

    def flush(self) -> None:
        """Flush all plugins — drains every subscribed operator's queue."""
        for op in self._all_operators:
            op.drain_plugin_queue()
        for plugin in self.plugins:
            plugin.flush()

    def close(self) -> None:
        """End the run, flush, and close all plugins. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self.end_run()
        self.flush()
        for plugin in self.plugins:
            plugin.close()
        for op in self._all_operators:
            op.shutdown_plugin_worker()


__all__ = ["ObsPluginSet", "load_obs_plugins"]
