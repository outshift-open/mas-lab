#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared MCE metric computation logic.

Used by both ``mas-lab eval-output`` (CLI) and ``EvalMceBatchStep`` (pipeline).

Session-level MCE metrics available
-------------------------------------
All metrics are LLM-as-judge (``mce_metrics_plugin``); they require a working
LLM service.  Call :func:`install_openai_llm_service` once per process before
computing.

Core session metrics:
- ``goal_success_rate``           — Did the agent accomplish the user's goal?
- ``groundedness``                — Is the response grounded in the retrieved context?
- ``response_completeness``       — Does the response address all aspects of the query?
- ``workflow_cohesion_index``     — How cohesive was multi-agent task coordination?
- ``workflow_efficiency``         — Was the workflow executed efficiently?
- ``consistency``                 — Were responses consistent across turns?
- ``context_preservation``        — Was conversational context preserved?
- ``information_retention``       — Was key information retained across turns?
- ``intent_recognition_accuracy`` — Was the user's intent correctly identified?
- ``component_conflict_rate``     — How often did component outputs conflict?

Note: ``task_delegation`` is NOT a session-level metric.
``TaskDelegationAccuracy`` exists in metrics_computation_engine as a span-level
stub (unfinished TODO prompt) and is not wired into this runner.
``answer_relevancy`` is now a session-level metric implemented in this runner.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric registry  (public: mce_metrics_plugin from agntcy/telemetry-hub)
# ---------------------------------------------------------------------------

METRIC_MAP: Dict[str, str] = {
    "answer_relevancy":            "mce_metrics_plugin.session.answer_relevancy:AnswerRelevancy",
    "goal_success_rate":           "mce_metrics_plugin.session.goal_success_rate:GoalSuccessRate",
    "groundedness":                "mce_metrics_plugin.session.groundedness:Groundedness",
    "response_completeness":       "mce_metrics_plugin.session.response_completeness:ResponseCompleteness",
    "workflow_cohesion_index":     "mce_metrics_plugin.session.workflow_cohesion_index:WorkflowCohesionIndex",
    "workflow_efficiency":         "mce_metrics_plugin.session.workflow_efficiency:WorkflowEfficiency",
    "consistency":                 "mce_metrics_plugin.session.consistency:Consistency",
    "context_preservation":        "mce_metrics_plugin.session.context_preservation:ContextPreservation",
    "information_retention":       "mce_metrics_plugin.session.information_retention:InformationRetention",
    "intent_recognition_accuracy": "mce_metrics_plugin.session.intent_recognition_accuracy:IntentRecognitionAccuracy",
    "component_conflict_rate":     "mce_metrics_plugin.session.component_conflict_rate:ComponentConflictRate",
}

ALL_SESSION_METRICS: List[str] = list(METRIC_MAP.keys())

# ---------------------------------------------------------------------------
# DeepEval — native continuous scoring (no BinaryGrading constraint)
# ---------------------------------------------------------------------------

# Metrics in this set are computed via deepeval when binary_grading=False.
# deepeval scores are natively continuous (AnswerRelevancyMetric = fraction of
# relevant statements; GEval = weighted rubric 0-1 float).
_DEEPEVAL_METRIC_NAMES = {"answer_relevancy", "goal_success_rate"}

_deepeval_model: Any = None   # deepeval GPTModel instance; set by install_openai_llm_service


def _make_deepeval_model(
    model: str,
    api_key: str,
    base_url: Optional[str],
) -> Any:
    """Build a ``deepeval.models.GPTModel`` from the resolved LLM config."""
    try:
        from deepeval.models import GPTModel
        return GPTModel(
            model=model,
            api_key=api_key,
            base_url=base_url or None,
        )
    except Exception as exc:
        logger.warning("deepeval GPTModel unavailable: %s", exc)
        return None


def _compute_deepeval_score(
    metric_name: str,
    input_query: str,
    final_response: str,
) -> Dict[str, Any]:
    """Compute a single metric via deepeval and return a runner-compatible dict.

    Returns ``{"value": float|None, "reasoning": str, "error": str|None}``.
    Score is natively 0.0–1.0 continuous (no BinaryGrading schema injected).
    """
    if os.environ.get("MAS_MCE_OFFLINE", "").lower() in ("1", "true", "yes"):
        if not (input_query or "").strip():
            return {"value": None, "reasoning": "", "error": "input_query_empty"}
        if not (final_response or "").strip():
            return {"value": None, "reasoning": "", "error": "final_response_empty"}
        return {
            "value": 0.75,
            "reasoning": "offline stub (MAS_MCE_OFFLINE)",
            "error": None,
        }

    if _deepeval_model is None:
        return {"value": None, "reasoning": "", "error": "deepeval model not initialised"}
    try:
        from deepeval.test_case import LLMTestCase
        test_case = LLMTestCase(input=input_query, actual_output=final_response)

        if metric_name == "answer_relevancy":
            from deepeval.metrics import AnswerRelevancyMetric
            metric = AnswerRelevancyMetric(
                model=_deepeval_model,
                async_mode=False,
                verbose_mode=False,
            )
        elif metric_name == "goal_success_rate":
            from deepeval.metrics import GEval
            from deepeval.test_case import LLMTestCaseParams
            metric = GEval(
                name="GoalSuccessRate",
                criteria=(
                    "Does the response correctly correspond to what the user asked for? "
                    "Does it fulfill all expectations specified in the goal? "
                    "If the assistant cannot achieve the goal, does it state why?"
                ),
                evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                model=_deepeval_model,
                async_mode=False,
                verbose_mode=False,
            )
        else:
            return {"value": None, "reasoning": "", "error": f"no deepeval impl for {metric_name!r}"}

        metric.measure(test_case, _show_indicator=False)
        return {
            "value":     float(metric.score),
            "reasoning": str(getattr(metric, "reason", "") or ""),
            "error":     None,
        }
    except Exception as exc:
        logger.error("deepeval metric %r failed: %s", metric_name, exc)
        return {"value": None, "reasoning": "", "error": str(exc)}


# ---------------------------------------------------------------------------
# LLM service setup (openai SDK via public metrics_computation_engine)
# ---------------------------------------------------------------------------

_jury: Any = None          # metrics_computation_engine.llm_judge.jury.Jury
_jury_patched = False


def install_openai_llm_service(
    model_override: Optional[str] = None,
    *,
    api_key_env: Optional[str] = None,
) -> None:
    """Create a ``Jury`` (public MCE) backed by the openai SDK.

    Patches ``LLMClient.query`` at class level so that all ``Jury`` instances
    route through our openai client (no litellm required).  Idempotent.

    Configuration resolution order:
      1. *model_override* argument
      2. ``config.yaml`` → InfraManifest
      3. Hard-coded fallback: ``vertex_ai/gemini-3-pro-preview``
    """
    global _jury, _jury_patched, _deepeval_model
    if _jury_patched and model_override is None and api_key_env is None:
        return

    infra_api_base, infra_api_key_env, infra_model = _resolve_infra()

    effective_model    = model_override or infra_model
    effective_api_base = infra_api_base or None
    effective_api_key  = (
        os.environ.get(api_key_env or infra_api_key_env)
        or os.environ.get("OPENAI_API_KEY")
        or "none"
    )

    from openai import OpenAI
    _client = OpenAI(api_key=effective_api_key, base_url=effective_api_base)

    from metrics_computation_engine.llm_judge.llm import LLMClient
    from metrics_computation_engine.llm_judge.jury import Jury

    def _query_patch(self: Any, messages: list, **kwargs: Any) -> Any:
        # Strip response_format — some proxies don't support JSON mode;
        # the prompt already instructs the model to return JSON.
        kwargs.pop("response_format", None)
        model = self.model or effective_model
        delay = _MCE_BASE_DELAY
        last_exc: Optional[Exception] = None
        for attempt in range(_MCE_MAX_RETRIES + 1):
            try:
                return _client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
            except Exception as exc:
                if not _is_ratelimit_error(exc) or attempt == _MCE_MAX_RETRIES:
                    raise RuntimeError(
                        f"MCE LLM call failed (model={model!r}): {exc}"
                    ) from exc
                jitter = random.uniform(0.0, delay * 0.25)
                wait = delay + jitter
                logger.warning(
                    "MCE rate-limit on attempt %d/%d — retrying in %.1fs (%s)",
                    attempt + 1, _MCE_MAX_RETRIES, wait, exc,
                )
                time.sleep(wait)
                delay = min(delay * 2.0, 120.0)
                last_exc = exc
        raise RuntimeError(
            f"MCE LLM call failed after {_MCE_MAX_RETRIES} retries: {last_exc}"
        )

    LLMClient.query = _query_patch  # type: ignore[method-assign]

    llm_config = {
        "LLM_MODEL_NAME":    effective_model,
        "LLM_BASE_MODEL_URL": effective_api_base or "",
        "LLM_API_KEY":       effective_api_key,
    }
    _jury = Jury(llm_config)

    # Build deepeval model from the same config so continuous metrics use the same LLM.
    _deepeval_model = _make_deepeval_model(
        model=effective_model,
        api_key=effective_api_key,
        base_url=effective_api_base or None,
    )

    _jury_patched = True
    logger.debug(
        "MCE Jury configured (model=%s, base_url=%s, deepeval=%s)",
        effective_model, effective_api_base, "ok" if _deepeval_model else "unavailable",
    )


def _resolve_infra() -> tuple[str, str, str]:
    """Resolve LLM proxy config from workspace ``config.yaml`` infra refs.

    Returns ``(api_base, api_key_env, model)``.
    """
    _FALLBACK = ("", "OPENAI_API_KEY", "gpt-4o")
    try:
        from mas.lab.workspace import WorkspaceConfig, workspace_get
        from mas.ctl.infra.resolve import resolve_infra_refs
        from mas.runtime.agent_defaults import resolve_default_model
    except ImportError:
        return _FALLBACK

    ws = WorkspaceConfig.load()
    if not ws.found:
        return _FALLBACK

    refs = ws.effective_infra_refs
    if not refs:
        return _FALLBACK

    try:
        resolved = resolve_infra_refs(refs, workspace=ws)
    except Exception as exc:
        logger.warning("Could not resolve infra refs %s: %s", refs, exc)
        return _FALLBACK

    proxy = resolved.llm_proxy
    return (
        proxy.get("api_base", ""),
        proxy.get("api_key_env") or "OPENAI_API_KEY",
        resolve_default_model(ws) or proxy.get("default_model") or "gpt-4o",
    )


# ---------------------------------------------------------------------------
# Rate-limit-aware LLM call helper
# ---------------------------------------------------------------------------

_MCE_MAX_RETRIES = 4
_MCE_BASE_DELAY  = 5.0   # seconds — doubles each retry, capped at 120 s


def _is_ratelimit_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a transient rate-limit / quota error.

    Checks for HTTP 429 or rate-limiting language in the error message.  HTTP
    401 alone is *not* treated as a rate-limit error — a plain auth failure
    (wrong API key) should fail immediately, not waste 4 retries.  The
    Outshift proxy signals budget exhaustion via a 401 whose message body
    contains "budget" or "quota", so those keywords still trigger a retry.
    """
    s = str(exc).lower()
    return any(tok in s for tok in ("429", "rate", "quota", "too many", "budget"))


def _llm_call_with_retry(client: Any, model: str, messages: list) -> str:
    """Call the OpenAI-compatible chat endpoint with exponential-backoff retry.

    Retries on rate-limit errors (HTTP 401 / 429 / quota messages) up to
    ``_MCE_MAX_RETRIES`` times.  Non-rate-limit errors are re-raised immediately.
    """
    delay = _MCE_BASE_DELAY
    last_exc: Optional[Exception] = None
    for attempt in range(_MCE_MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(model=model, messages=messages)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            if not _is_ratelimit_error(exc) or attempt == _MCE_MAX_RETRIES:
                raise RuntimeError(
                    f"MCE LLM call failed (model={model!r}): {exc}"
                ) from exc
            jitter = random.uniform(0.0, delay * 0.25)
            wait = delay + jitter
            logger.warning(
                "MCE rate-limit on attempt %d/%d — retrying in %.1fs (%s)",
                attempt + 1, _MCE_MAX_RETRIES, wait, exc,
            )
            time.sleep(wait)
            delay = min(delay * 2.0, 120.0)
            last_exc = exc
    # Should never reach here
    raise RuntimeError(
        f"MCE LLM call failed after {_MCE_MAX_RETRIES} retries (model={model!r}): {last_exc}"
    )


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_session_metrics(
    trace_path: Path,
    metric_names: List[str],
    response_agent_id: Optional[str] = None,
    *,
    binary_grading: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Compute MCE metrics for one trace file.

    Returns a dict mapping metric_id → ``{"value": float|None, "reasoning": str, "error": str|None}``.

    *response_agent_id* is forwarded to :class:`MASTraceProvider`.  When
    ``None`` (default), the root agent is auto-detected from the trace.

    *binary_grading* controls the scoring backend:

    * ``False`` (default) — metrics with a native deepeval implementation
      (``answer_relevancy``, ``goal_success_rate``) are computed via deepeval,
      which returns continuous 0.0–1.0 scores without any BinaryGrading schema.
      Other metrics fall back to MCE with BinaryGrading.
    * ``True`` — all metrics use MCE BinaryGrading (0 or 1 integer).
    """
    from mas.library.eval.mce.trace_provider import MASTraceProvider
    provider = MASTraceProvider(response_agent_id=response_agent_id)
    context  = provider.fetch(str(trace_path), requirements=None)
    resource_id = _run_id_from_path(trace_path)
    # Inject session_id so MCE polymorphic metrics (Duration, Cost…) can
    # detect the resource type via _detect_resource_type().
    context["session_id"] = resource_id

    _input_query_missing = not context.get("input_query")
    _final_response_missing = not context.get("final_response")
    if _input_query_missing:
        logger.debug("%s — input_query empty", trace_path)
    if _final_response_missing:
        logger.debug("%s — final_response empty (response_agent=%r)",
                     trace_path, response_agent_id or "<auto>")

    # Build a minimal SessionEntity from the context dict.
    # LLM-as-judge metrics need input_query, final_response, session_id, and
    # conversation_data for metrics that use conversation_data.get("conversation")
    # or conversation_data.get("elements") (e.g. WorkflowCohesionIndex,
    # ResponseCompleteness, Groundedness).
    from metrics_computation_engine.entities.models.session import SessionEntity
    conversation_text = context.get("conversation_text") or ""
    session = SessionEntity(
        session_id=resource_id,
        spans=[],  # required by pydantic; LLM-judge metrics only use input_query / final_response
        input_query=context.get("input_query") or "",
        final_response=context.get("final_response") or "",
        conversation_data={
            "conversation": conversation_text,
            "elements": conversation_text,
        } if conversation_text else None,
    )

    import asyncio
    # compute() is async in the public package; run synchronously in a dedicated loop
    # (safe because this function is called from a ThreadPoolExecutor thread).
    loop = asyncio.new_event_loop()

    results: Dict[str, Dict[str, Any]] = {}

    try:
        for name in metric_names:
            # Prefer deepeval for continuous-capable metrics when not in binary mode.
            if not binary_grading and name in _DEEPEVAL_METRIC_NAMES:
                if not (context.get("input_query") or "").strip():
                    results[name] = {
                        "value": None,
                        "reasoning": "",
                        "error": "input_query_empty",
                    }
                    continue
                if not (context.get("final_response") or "").strip():
                    results[name] = {
                        "value": None,
                        "reasoning": "",
                        "error": "final_response_empty",
                    }
                    continue
                results[name] = _compute_deepeval_score(
                    name,
                    context.get("input_query") or "",
                    context.get("final_response") or "",
                )
                continue

            metric_cls = _import_metric(name)
            if metric_cls is None:
                results[name] = {"value": None, "reasoning": "", "error": f"import failed: {name}"}
                continue
            try:
                metric = metric_cls()
                metric.init_with_model(_jury)
                outcome = loop.run_until_complete(metric.compute(session))
                results[name] = {
                    "value":     float(outcome.value) if outcome.value is not None else None,
                    "reasoning": str(outcome.reasoning or ""),
                    "error":     str(outcome.error_message) if outcome.error_message else None,
                }
            except Exception as exc:
                logger.error("MCE metric %r failed on %s: %s", name, trace_path, exc)
                results[name] = {"value": None, "reasoning": "", "error": str(exc)}
    finally:
        loop.close()

    # Build run-quality metadata: warnings (data issues) + errors (metric failures)
    warnings: List[str] = []
    if _input_query_missing:
        warnings.append("input_query_empty")
    if _final_response_missing:
        warnings.append("final_response_empty")
    metric_errors = [name for name, v in results.items() if v.get("error")]
    results["__run_quality__"] = {
        "warnings": warnings,
        "errors":   metric_errors,
        "status":   "error" if metric_errors else ("warn" if warnings else "ok"),
    }

    return results


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

METRICS_SCHEMA_VERSION = "1"


def build_metrics_document(
    item_id: str,
    scenario: str,
    session_scores: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the canonical ``metrics.json`` document (schema v1)."""
    run_quality = session_scores.get("__run_quality__", {"warnings": [], "errors": [], "status": "ok"})
    session = {k: v for k, v in session_scores.items() if not k.startswith("__")}
    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        "item_id":        item_id,
        "scenario":       scenario,
        "session":        session,
        "run_quality":    run_quality,
        "computed_at":    datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _import_metric(name: str):
    """Import and return the MCE metric class for *name*, or ``None`` on failure."""
    spec = METRIC_MAP.get(name)
    if not spec:
        logger.warning("Unknown MCE metric: %r.  Known: %s", name, list(METRIC_MAP))
        return None
    module_path, cls_name = spec.rsplit(":", 1)
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name)
    except Exception as exc:
        logger.error("Import error for MCE metric %r (%s): %s", name, spec, exc)
        return None


def _run_id_from_path(trace_path: Path) -> str:
    """Derive a human-readable run_id from the traces/events.jsonl path.

    E.g. ``baseline/item1/r1/traces/events.jsonl`` → ``baseline__item1__r1``.
    """
    parts = trace_path.parts
    # Find traces/ directory in path components
    try:
        idx = list(parts).index("traces")
        relevant = parts[max(0, idx - 3) : idx]
        return "__".join(relevant)
    except ValueError:
        return trace_path.parent.parent.name
