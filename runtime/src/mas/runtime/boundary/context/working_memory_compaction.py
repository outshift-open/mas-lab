#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""``spec.working_memory.compaction`` facade over ``context_manager``/``CMFactory``.

Translates the discoverable, working-memory-scoped compaction config into
the ``context_manager`` binding shape ``CMFactory``/the plugin registry
already understand (``StackConversation`` / ``SlidingWindowConversation`` /
``SummarizingConversation`` in ``library-standard/.../plugins/context/
conversation.py``). No new compaction engine — this is sugar, not a rewrite.
See ``docs/design/working-memory-compaction.md``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mas.runtime.boundary.context.trim import (
    CONTEXT_MANAGER_TYPE_SUMMARISING,
    is_summarising_context_manager,
)
from mas.runtime.engine.protocol import CompactionSummarizeEngine

logger = logging.getLogger(__name__)

# working_memory.compaction.strategy -> context_manager plugin type. Kept
# distinct from the registry's own type vocabulary (stack/sliding_window/
# summarising) so a manifest author reads intent, not implementation names.
_STRATEGY_TO_CM_TYPE: dict[str, str] = {
    "keep_recent": "stack",
    "sliding_window": "sliding_window",
    "summarize": CONTEXT_MANAGER_TYPE_SUMMARISING,
}

# Which compaction sub-keys become which context_manager param, per strategy.
_STRATEGY_PARAM_KEYS: dict[str, tuple[str, ...]] = {
    "keep_recent": ("max_messages",),
    "sliding_window": ("window_size",),
    "summarize": ("summary_threshold", "keep_turns"),
}

SUMMARIZE_INSTRUCTIONS = (
    "Summarize the following conversation turns concisely, preserving key "
    "facts, decisions, and any identifiers (names, IDs, numbers) a later "
    "turn might need to reference. Write plain prose, not a transcript."
)


@dataclass(frozen=True)
class WorkingMemoryCompactionRuntime:
    """Commit-time compaction of the cross-turn working-memory buffer.

    Manifest authors set ``spec.working_memory.compaction`` (or an explicit
    ``summarising`` ``context_manager``). ``summarize_fn`` is engine wiring —
    not a manifest field — and belongs on working memory, not on the context
    manager plugin surface (``ContextManagerContract`` shapes history at
    assembly; it is not a context source).
    """

    summary_threshold: int
    keep_turns: int
    summarize_fn: Callable[[list[dict[str, Any]]], str]


def working_memory_compaction_runtime(spec: dict[str, Any]) -> WorkingMemoryCompactionRuntime | None:
    """Resolved commit-time compaction after ``apply_working_memory_compaction``."""
    cm = spec.get("context_manager")
    if not isinstance(cm, dict) or not is_summarising_context_manager(cm):
        return None
    params = cm.get("params") or {}
    summarize_fn = params.get("summarize_fn")
    if not callable(summarize_fn):
        return None
    try:
        raw_threshold = params.get("summary_threshold")
        raw_keep = params.get("keep_turns")
        threshold = int(raw_threshold) if raw_threshold is not None else 4000
        keep = int(raw_keep) if raw_keep is not None else 10
    except (TypeError, ValueError):
        return None
    return WorkingMemoryCompactionRuntime(
        summary_threshold=threshold,
        keep_turns=keep,
        summarize_fn=summarize_fn,
    )


def context_manager_binding_from_compaction(compaction: dict[str, Any]) -> dict[str, Any]:
    """Translate one ``working_memory.compaction`` block into a
    ``context_manager``-shaped binding: ``{"type": ..., "params": {...}}``.
    """
    strategy = str(compaction.get("strategy") or "keep_recent").strip()
    cm_type = _STRATEGY_TO_CM_TYPE.get(strategy)
    if cm_type is None:
        raise ValueError(
            f"unknown working_memory.compaction.strategy: {strategy!r} "
            f"(expected one of {sorted(_STRATEGY_TO_CM_TYPE)})"
        )
    param_keys = _STRATEGY_PARAM_KEYS.get(strategy, ())
    params = {k: compaction[k] for k in param_keys if k in compaction}
    return {"type": cm_type, "params": params}


def resolve_working_memory_context_manager(spec: dict[str, Any]) -> dict[str, Any] | None:
    """If ``spec.working_memory.compaction`` is set and ``spec.context_manager``
    isn't already explicit, return the equivalent ``context_manager`` binding
    to splice in. Returns ``None`` when there's nothing to do (no compaction
    configured, or the manifest already sets context_manager directly --
    that always wins).
    """
    if spec.get("context_manager"):
        return None
    working_memory = spec.get("working_memory")
    if not isinstance(working_memory, dict):
        return None
    compaction = working_memory.get("compaction")
    if not isinstance(compaction, dict):
        return None
    return context_manager_binding_from_compaction(compaction)


def build_llm_summarize_fn(engine: CompactionSummarizeEngine) -> Callable[[list[dict[str, Any]]], str]:
    """Return ``engine.summarize_messages`` for ``SummarizingConversation`` wiring."""
    if not isinstance(engine, CompactionSummarizeEngine):
        raise TypeError(f"{type(engine).__name__} does not implement CompactionSummarizeEngine")
    return engine.summarize_messages


def _wire_summarize_fn(binding: dict[str, Any], engine: Any) -> dict[str, Any]:
    """Attach ``summarize_fn`` to a ``summarising`` context_manager binding."""
    if not is_summarising_context_manager(binding):
        return binding
    params = dict(binding.get("params") or {})
    if callable(params.get("summarize_fn")):
        return {**binding, "params": params}
    if isinstance(engine, CompactionSummarizeEngine):
        params["summarize_fn"] = engine.summarize_messages
        return {**binding, "params": params}
    logger.warning(
        "context_manager.type=summarising needs an engine implementing "
        "CompactionSummarizeEngine; none available — falling back to keep_recent "
        "(unbounded history, no compaction)."
    )
    return {"type": "stack", "params": {}}


def apply_working_memory_compaction(spec: dict[str, Any], *, engine: Any = None) -> None:
    """Mutate ``spec`` in place: resolve ``context_manager`` from WM compaction
    sugar when needed, then wire ``summarize_fn`` for ``SummarizingConversation``.

    Author-facing config lives under ``spec.working_memory.compaction``. The
    translated ``context_manager`` binding is the assembly-time plugin hook
    only; commit-time chunk compaction reads ``working_memory_compaction_runtime``
    on ``AutoCtxAssembler`` instead.
    """
    binding = resolve_working_memory_context_manager(spec)
    if binding is not None:
        spec["context_manager"] = _wire_summarize_fn(binding, engine)
        return
    cm = spec.get("context_manager")
    if isinstance(cm, dict):
        spec["context_manager"] = _wire_summarize_fn(cm, engine)
