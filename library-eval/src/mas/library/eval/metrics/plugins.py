#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Load ``eval_metric`` plugins onto the existing eval provider (default ``mce``)."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Iterable

from mas.library.eval.evaluator import DEFAULT_METRIC_PROVIDER, get_provider
from mas.library.eval.metrics import EvalMetric

logger = logging.getLogger(__name__)

_LOADED_PLUGINS = False


def reset_metrics_for_tests() -> None:
    """Drop hosted custom metrics. Tests only.

    Marks plugins as already loaded so isolated unit tests do not pull
    workspace ``eval_metric`` entries. Stock MCE ids stay on the provider.
    """
    global _LOADED_PLUGINS
    try:
        host = get_provider(DEFAULT_METRIC_PROVIDER)
        host._hosted_metrics().clear()
    except (ValueError, RuntimeError):
        logger.debug("reset_metrics_for_tests: provider unavailable", exc_info=True)
    _LOADED_PLUGINS = True


def load_declared_eval_metrics(*, force: bool = False) -> None:
    """Walk ``eval_metric`` plugins and register each metric on its provider."""
    global _LOADED_PLUGINS
    if _LOADED_PLUGINS and not force:
        return
    _LOADED_PLUGINS = True
    try:
        from mas.runtime.registry import get_registry

        registry = get_registry()
    except Exception:
        logger.debug("eval_metric plugin load skipped (no registry)", exc_info=True)
        return
    try:
        for entry in registry.get_by_category("eval_metric"):
            _register_plugin_entry(entry)
    except Exception:
        logger.debug("eval_metric plugin walk failed", exc_info=True)


def _register_plugin_entry(entry: Any) -> None:
    attrs = dict(entry.attributes or {})
    provider_name = str(attrs.get("provider") or DEFAULT_METRIC_PROVIDER).strip() or DEFAULT_METRIC_PROVIDER
    provider = get_provider(provider_name)
    for metric in _metrics_from_entry(entry):
        provider.register_metric(metric)


def _metrics_from_entry(entry: Any) -> Iterable[EvalMetric]:
    attrs = dict(entry.attributes or {})
    factory = str(attrs.get("factory") or "").strip()
    default = entry.default
    if factory:
        if ":" in factory:
            module_name, func_name = factory.rsplit(":", 1)
        else:
            module_name, func_name = default.module, default.class_name or "build_metrics"
        fn = getattr(importlib.import_module(module_name), func_name)
        produced = fn()
        return list(produced)
    cls = default.load_class()
    try:
        produced = cls.build_metrics()
    except AttributeError:
        produced = None
    if produced is not None:
        return list(produced)
    instance = cls()
    if isinstance(instance, EvalMetric):
        return [instance]
    raise TypeError(
        f"eval_metric plugin {entry.urn} must be an EvalMetric, expose "
        "build_metrics(), or set attributes.factory to a callable"
    )
