"""Attribute key constants for OTel span processing.

All attribute key strings used across the observability normalizer live here.
Import from this module to avoid typos and enable IDE autocomplete.
"""

from __future__ import annotations


class IoaObserveAttrs:
    """Attribute keys emitted by the ioa_observe / MAS SDK instrumentation."""

    SPAN_KIND = "ioa_observe.span.kind"
    SPAN_KIND_LEGACY = "traceloop.span.kind"
    ENTITY_NAME = "ioa_observe.entity.name"
    ENTITY_NAME_LEGACY = "traceloop.entity.name"
    ENTITY_INPUT = "ioa_observe.entity.input"
    ENTITY_OUTPUT = "ioa_observe.entity.output"
    AGENT_SEQUENCE = "ioa_observe.agent.sequence"
    FORK_ID = "ioa_observe.fork.id"
    FORK_BRANCH = "ioa_observe.fork.branch_index"
    FORK_PARENT_NAME = "ioa_observe.fork.parent_name"
    FORK_PARENT_SEQ = "ioa_observe.fork.parent_sequence"
    JOIN_FORK_ID = "ioa_observe.join.fork_id"
    JOIN_BRANCH_CNT = "ioa_observe.join.branch_count"


class GenAIAttrs:
    """OpenTelemetry GenAI semantic convention attributes."""

    OPERATION = "gen_ai.operation.name"
    SYSTEM = "gen_ai.system"
    REQ_MODEL = "gen_ai.request.model"
    RESP_MODEL = "gen_ai.response.model"
    IN_TOKENS = "gen_ai.usage.input_tokens"
    OUT_TOKENS = "gen_ai.usage.output_tokens"
    TOTAL_TOKENS = "gen_ai.usage.total_tokens"


class MasBoundaryAttrs:
    """MAS SDK boundary and identity attributes."""

    BOUNDARY = "mas.boundary"
    CALL_ID = "mas.call.id"
    AGENT_ID = "mas.agent.id"
    SESSION_ID = "mas.session.id"


class RoutingAttrs:
    """Routing / communication attributes set by ObserveSDKPlugin."""

    FROM = "routing.from_agent"
    TO = "routing.to_agent"
    TASK = "routing.task"


class LinkAttrs:
    """OTel span Link attribute keys."""

    TYPE = "link.type"
    FROM_AGENT = "link.from_agent"


class InsightClawAttrs:
    """Attribute keys (and one span name) added by InsightClaw span extensions.

    InsightClaw is a real OTel SDK instrumentation (patches OpenLLMetry/openai
    SDK spans via ``tracer.startSpan``/``span.setAttribute`` -- see
    insightClaw/observability-plugin/src/hooks.ts) that layers its own
    ``openclaw.*`` attributes on top of base OTel + GenAI semconv + ioa_observe
    attributes on the SAME span -- not a different span shape or wire format.
    Verified against InsightClaw's actual source (2026-08-26); this is an
    open-ended, additive set -- InsightClaw's real vocabulary is much larger
    (subagent spawning, memory/context metrics, diagnostics) than what's
    ported here, which covers only what the KG normalizer currently acts on.
    """

    MAS_CALL_SPAN_NAME = "openclaw.request"
    TOOL_NAME = "openclaw.tool.name"
    TOOL_CALL_ID = "openclaw.tool.call_id"
    TOOL_IS_SYNTHETIC = "openclaw.tool.is_synthetic"
    TOOL_RESULT_CHARS = "openclaw.tool.result_chars"
    TOOL_RESULT_PARTS = "openclaw.tool.result_parts"
    SESSION_KEY = "openclaw.session.key"
    MESSAGE_CHANNEL = "openclaw.message.channel"
    MESSAGE_DIRECTION = "openclaw.message.direction"
    MESSAGE_FROM = "openclaw.message.from"
    HANDOFF_SOURCE_AGENT = "openclaw.handoff.source_agent"
    # NOTE: verified real key is source_runtime_session, not source_session
    # (insightClaw/observability-plugin/src/hooks.ts:2728-2883).
    HANDOFF_SOURCE_SESSION = "openclaw.handoff.source_runtime_session"


# Span names in ioa_observe format that carry no semantic content
SUPPRESSED_IOA_OBSERVE_NAMES: frozenset = frozenset({"agent_start_event", "agent_end_event"})
