#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCE CamelCase API — session metrics + wired span/session core metrics."""
from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from metrics_computation_engine.entities.models.session import SessionEntity
from metrics_computation_engine.models.eval import MetricResult
from metrics_computation_engine.models.requests import LLMJudgeConfig

logger = logging.getLogger(__name__)

# Session and span metrics from telemetry-hub PyPI packages (MCE v1).
# Labs use the session-level judge metrics; span stubs not used in OSS benches
# are omitted here rather than re-wrapped in mas-lab.
METRIC_REGISTRY: Dict[str, str] = {
    "GoalSuccessRate": "mce_metrics_plugin.session.goal_success_rate:GoalSuccessRate",
    "Groundedness": "mce_metrics_plugin.session.groundedness:Groundedness",
    "ResponseCompleteness": "mce_metrics_plugin.session.response_completeness:ResponseCompleteness",
    "ContextPreservation": "mce_metrics_plugin.session.context_preservation:ContextPreservation",
    "IntentRecognitionAccuracy": "mce_metrics_plugin.session.intent_recognition_accuracy:IntentRecognitionAccuracy",
    "WorkflowCohesionIndex": "mce_metrics_plugin.session.workflow_cohesion_index:WorkflowCohesionIndex",
    "Consistency": "mce_metrics_plugin.session.consistency:Consistency",
    "InformationRetention": "mce_metrics_plugin.session.information_retention:InformationRetention",
    "WorkflowEfficiency": "mce_metrics_plugin.session.workflow_efficiency:WorkflowEfficiency",
    "ComponentConflictRate": "mce_metrics_plugin.session.component_conflict_rate:ComponentConflictRate",
    "ToolUtilizationAccuracy": "metrics_computation_engine.metrics.span.tool_utilization_accuracy:ToolUtilizationAccuracy",
    "ToolError": "metrics_computation_engine.metrics.span.tool_error:ToolError",
    "ToolErrorRate": "metrics_computation_engine.metrics.session.tool_error_rate:ToolErrorRate",
    "AgentToAgentInteractions": "metrics_computation_engine.metrics.session.agent_to_agent_interactions:AgentToAgentInteractions",
    "AgentToToolInteractions": "metrics_computation_engine.metrics.session.agent_to_tool_interactions:AgentToToolInteractions",
    "CyclesCount": "metrics_computation_engine.metrics.session.cycles:CyclesCount",
}


async def compute_session_metrics(
    session: SessionEntity,
    metrics: List[str],
    llm_config: Dict[str, Any] | LLMJudgeConfig,
    *,
    include_reasoning: bool = True,
) -> List[MetricResult]:
    """Compute MCE metrics on a :class:`SessionEntity`."""
    del include_reasoning  # reserved for future judge options
    if isinstance(llm_config, dict):
        llm_config = LLMJudgeConfig(**llm_config)

    results: List[MetricResult] = []
    for metric_name in metrics:
        metric_cls = _import_metric(metric_name)
        if metric_cls is None:
            logger.error("Unknown metric: %s", metric_name)
            continue

        try:
            metric = metric_cls()
            if hasattr(metric, "create_model"):
                model = metric.create_model(llm_config)
                metric.init_with_model(model)
            result = await metric.compute(session)
            results.append(result)
        except Exception as exc:
            logger.error("Metric %s failed: %s", metric_name, exc, exc_info=True)
            results.append(
                MetricResult(
                    metric_name=metric_name,
                    value=None,
                    aggregation_level="session",
                    category="error",
                    app_name=getattr(session, "app_name", "unknown"),
                    description=f"Computation failed: {exc}",
                    unit="",
                    reasoning="",
                    span_id="",
                    session_id=[session.session_id],
                    source="native",
                    entities_involved=[],
                    edges_involved=[],
                    success=False,
                    metadata={},
                    error_message=str(exc),
                )
            )

    return results


def build_session_from_trace(
    trace_path: str | Path,
    *,
    session_id_filter: Optional[str] = None,
) -> SessionEntity:
    """Build a :class:`SessionEntity` from ``events.jsonl``."""
    from metrics_computation_engine.entities.core.trace_processor import (
        TraceProcessor,
        create_pseudo_grouped_sessions_from_file,
    )

    from mas.library.eval.mce.trace_provider import MASTraceProvider

    trace_path = Path(trace_path)
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    raw_traces: List[Dict[str, Any]] = []
    with trace_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw_traces.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not raw_traces:
        raise ValueError(f"No valid traces found in {trace_path}")

    grouped_sessions = create_pseudo_grouped_sessions_from_file(raw_traces)
    processor = TraceProcessor()
    session_set = processor.process_grouped_sessions(
        grouped_sessions,
        session_id_filter=session_id_filter,
    )
    if not session_set.sessions:
        raise ValueError(f"No sessions found in trace {trace_path}")

    session = session_set.sessions[0]
    provider = MASTraceProvider()
    ctx = provider.fetch(str(trace_path), requirements=None)
    tool_spans = ctx.get("tool_spans") or []
    if tool_spans and not getattr(session, "spans", None):
        session.spans = tool_spans
    return session


def _import_metric(name: str):
    spec = METRIC_REGISTRY.get(name)
    if not spec:
        logger.warning("Unknown metric: %s. Known: %s", name, list(METRIC_REGISTRY.keys()))
        return None
    module_path, cls_name = spec.rsplit(":", 1)
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name)
    except Exception as exc:
        logger.error("Import error for metric %s (%s): %s", name, spec, exc)
        return None
