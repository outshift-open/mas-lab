#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Generic evaluation module — provider-agnostic metric computation.

Entry point for computing quality metrics from a knowledge graph.

Usage::

    from mas.library.eval.evaluator import evaluate_run, get_provider

    scores = evaluate_run(
        kg_path=Path("output/baseline/item1/r1/kg.json"),
        metrics=["GoalSuccessRate", "Groundedness"],
        provider="mce",
    )
    # {"GoalSuccessRate": {"value": 0.85, "reasoning": "...", "error": None}}

Provider selection (explicit — no auto-fallback)::

    evaluate_run(kg_path, metrics, provider="mce")       # mce meta-package
    evaluate_run(kg_path, metrics, provider="mce_oss")   # metrics_computation_engine (OSS)
"""
from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)


class MetricScore(TypedDict):
    value: Optional[float]
    reasoning: str
    error: Optional[str]


class EvalProvider(ABC):
    """Abstract evaluation provider — computes metrics from a KG."""

    name: str = ""
    """Provider identifier (e.g. 'mce', 'mce_oss')."""

    @abstractmethod
    def compute(
        self,
        kg_path: Path,
        metric_names: List[str],
        *,
        response_agent_id: Optional[str] = None,
    ) -> Dict[str, MetricScore]:
        """Compute metrics for a single run from its knowledge graph.

        Returns metric_id → {value, reasoning, error}.
        """

    @abstractmethod
    def available_metrics(self) -> List[str]:
        """Return the list of metric IDs this provider supports."""


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_BUILTIN_PROVIDERS: Dict[str, str] = {
    "mce": "mas.library.eval.providers.mce",
    "mce_oss": "mas.library.eval.providers.mce_oss",
    "mce_v1": "mas.library.eval.providers.mce",
    "adversarial": "mas.library.eval.providers.adversarial",
}

_BUILTIN_CLASSES: Dict[str, str] = {
    "mce": "MCEProvider",
    "mce_oss": "MCEOSSProvider",
    "mce_v1": "MCEProvider",
    "adversarial": "AdversarialProvider",
}

# Runtime registry — populated by register_provider().  Lab pipeline steps load
# domain-specific providers from lab-local files and register them here so that
# get_provider(name) works for the lifetime of the process without modifying
# the core evaluator module.
_RUNTIME_PROVIDERS: Dict[str, EvalProvider] = {}


def register_provider(name: str, provider: EvalProvider) -> None:
    """Register a provider instance with the MCE wrapper at runtime.

    Called by pipeline steps that load lab-local provider implementations
    (e.g. ``eval_trip_planner_gt`` loading from ``eval/trip_planner_gt.py``).
    After registration, ``get_provider(name)`` returns this instance for the
    lifetime of the process.

    Args:
        name:     Provider identifier, e.g. ``"trip_planner_gt"``.
        provider: Fully-initialised EvalProvider instance.
    """
    _RUNTIME_PROVIDERS[name] = provider


def list_available_providers() -> List[str]:
    """Return provider names that can be instantiated in this environment."""
    available = sorted(_RUNTIME_PROVIDERS.keys())
    for name, module_path in _BUILTIN_PROVIDERS.items():
        if name in _RUNTIME_PROVIDERS:
            continue
        try:
            importlib.import_module(module_path)
            available.append(name)
        except ImportError:
            continue
    return sorted(set(available))


def get_provider(name: Optional[str] = None, **kwargs: Any) -> EvalProvider:
    """Instantiate an evaluation provider by name.

    Args:
        name: Provider id, e.g. ``"mce"``, ``"mce_oss"``, or ``"adversarial"``.
              Required — there is no ``"auto"`` fallback chain.
        **kwargs: Constructor arguments forwarded to built-in providers
              (e.g. ``dataset_path`` for ``"adversarial"``).

    Raises:
        ValueError: If *name* is missing or unknown.
        RuntimeError: If the provider's dependencies are not installed.
    """
    if not name or name == "auto":
        available = list_available_providers()
        raise ValueError(
            "Evaluation provider is required (no auto-fallback). "
            f"Available providers: {', '.join(available) or '(none — install mce or metrics_computation_engine)'}"
        )
    if name in _RUNTIME_PROVIDERS and not kwargs:
        return _RUNTIME_PROVIDERS[name]
    return _make_provider(name, **kwargs)


def _make_provider(name: str, **kwargs: Any) -> EvalProvider:
    """Import and instantiate a provider.

    Raises:
        ValueError: Unknown provider name.
        RuntimeError: Dependencies missing (ImportError).
    """
    if name in _RUNTIME_PROVIDERS and not kwargs:
        return _RUNTIME_PROVIDERS[name]
    if name not in _BUILTIN_PROVIDERS:
        available = list_available_providers()
        raise ValueError(
            f"Unknown eval provider: {name!r}. "
            f"Available providers: {', '.join(available) or '(none)'}"
        )
    module_path = _BUILTIN_PROVIDERS[name]
    class_name = _BUILTIN_CLASSES[name]
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise RuntimeError(
            f"Eval provider {name!r} is not available — missing dependencies. "
            f"Install the package for {module_path}."
        ) from exc
    cls = getattr(mod, class_name)
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------

def evaluate_run(
    kg_path: Path,
    metrics: List[str],
    *,
    provider: Optional[str] = None,
    response_agent_id: Optional[str] = None,
) -> Dict[str, MetricScore]:
    """Compute metrics for a single run from its knowledge graph.

    Args:
        kg_path: Path to kg.json (output of normalize_events step).
        metrics: List of metric IDs to compute.
        provider: Provider id (``"mce"``, ``"mce_oss"``, etc.) — required.
        response_agent_id: Override root agent detection.

    Returns:
        Dict mapping metric_id → {value, reasoning, error}.
    """
    p = get_provider(provider)
    logger.info("evaluate_run: provider=%s, kg=%s, metrics=%s", p.name, kg_path, metrics)
    return p.compute(kg_path, metrics, response_agent_id=response_agent_id)


def list_metrics(provider: Optional[str] = None) -> List[str]:
    """Return available metric IDs from the selected provider."""
    return get_provider(provider).available_metrics()
