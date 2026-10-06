"""Typed exception hierarchy for the OTel → KG normalization pipeline."""

from __future__ import annotations


class KGNormalizationError(Exception):
    """Base for all OTel → KG normalization errors."""


class OtelSchemaError(KGNormalizationError):
    """A span does not conform to the expected OTel wire format."""

    def __init__(self, span_id: str, field: str, detail: str) -> None:
        self.span_id = span_id
        self.field = field
        super().__init__(f"[span={span_id}] field={field!r}: {detail}")


class OtelFormatError(KGNormalizationError):
    """Span list does not match any recognised span shape."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Cannot determine span shape: {detail}. "
            "Recognised shapes: a ClickHouse-exported row "
            "(SpanName/SpanAttributes keys) or a standard OTel SDK span "
            "(name/attributes/context keys). Every OTel span, regardless of "
            "which layer's attributes it carries (base/GenAI, ioa_observe, "
            "InsightClaw, mas.*), uses one of these two shapes."
        )


class UnknownSpanNameError(KGNormalizationError):
    """Span name has no entry in OPENCLAW_SPAN_TO_KIND_BASE and matches no
    other dispatch rule (name suffix, ioa_observe.span.kind, mas.boundary)."""

    def __init__(self, span_name: str, span_id: str) -> None:
        self.span_name = span_name
        self.span_id = span_id
        super().__init__(
            f"[span={span_id}] Unknown SpanName={span_name!r}. "
            "Recognised OTel span names are owned by norm "
            "(see norm.ioa_observe.build)."
        )


class UnknownSpanBoundaryError(KGNormalizationError):
    """mas.boundary value (or event kind) has no entry in the current mapping table."""

    def __init__(self, boundary: str, span_id: str) -> None:
        self.boundary = boundary
        self.span_id = span_id
        super().__init__(
            f"[span={span_id}] Unknown mas.boundary={boundary!r}. "
            "Add it to core/event_mappings.py:KIND_TO_CLASS "
            "(native event-kind normalization)."
        )


class MissingCallIdError(KGNormalizationError):
    """call_id is absent on a span that requires one."""

    def __init__(self, kind: str, agent_id: str, span_id: str) -> None:
        self.kind = kind
        self.agent_id = agent_id
        self.span_id = span_id
        super().__init__(
            f"[span={span_id}] kind={kind!r} agent={agent_id!r} has no call_id. "
            "The runtime must emit mas.call.id on every structural span."
        )
