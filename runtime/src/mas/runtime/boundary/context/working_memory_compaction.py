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

import json
import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# working_memory.compaction.strategy -> context_manager plugin type. Kept
# distinct from the registry's own type vocabulary (stack/sliding_window/
# summarising) so a manifest author reads intent, not implementation names.
_STRATEGY_TO_CM_TYPE: dict[str, str] = {
    "keep_recent": "stack",
    "sliding_window": "sliding_window",
    "summarize": "summarising",
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


def build_llm_summarize_fn(engine: Any) -> Callable[[list[dict[str, Any]]], str]:
    """A ``SummarizingConversation``-compatible ``summarize_fn`` backed by
    ``engine``'s own configured model -- no separate model-selection surface.

    Reuses ``LiveLlmEngine``'s existing completion primitives
    (``_model_access_chat``/``_chat_completion``) rather than the full
    ``InvokeEngineIo``/kernel turn machinery, since this is a one-off,
    out-of-band call made during context assembly, not a tracked turn. It
    still goes through the engine's own ``BudgetTracker`` (``allow_llm``/
    ``note_llm``) so a manifest's ``spec.budget.max_llm_calls`` ceiling can't
    be silently exceeded by summarization calls the budget never sees.
    """

    def summarize_fn(messages: list[dict[str, Any]]) -> str:
        budget = getattr(engine, "_budget", None)
        if budget is not None and not budget.allow_llm():
            raise RuntimeError(
                "working_memory compaction summarize_fn: LLM call budget "
                "exceeded (spec.budget.max_llm_calls)"
            )
        prompt = [
            {"role": "system", "content": SUMMARIZE_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(messages, default=str)},
        ]
        if budget is not None:
            budget.note_llm()
        logger.debug("working_memory compaction: summarizing %d message(s) via LLM", len(messages))
        if getattr(engine, "_uses_model_access", None) and engine._uses_model_access():
            message = engine._model_access_chat(prompt, tools=None, temperature=0.0)
        else:
            api_key = os.environ.get(getattr(engine, "api_key_env", ""), "")
            message = engine._chat_completion(prompt, api_key=api_key, tools=None, temperature=0.0)
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
        return str(content or "").strip()

    return summarize_fn


def apply_working_memory_compaction(spec: dict[str, Any], *, engine: Any = None) -> None:
    """Mutate ``spec`` in place: synthesize ``spec.context_manager`` from
    ``spec.working_memory.compaction`` when applicable (see
    ``resolve_working_memory_context_manager``).

    When the resolved strategy is ``summarize``, a real ``summarize_fn`` is
    wired in only if ``engine`` looks like a live LLM engine (has the
    completion primitives ``build_llm_summarize_fn`` needs) -- a mock/
    simulated engine has no model to call, so compaction degrades to
    ``keep_recent`` with a warning rather than crashing at first use.
    """
    binding = resolve_working_memory_context_manager(spec)
    if binding is None:
        return
    if binding["type"] == "summarising":
        if engine is not None and hasattr(engine, "_chat_completion"):
            binding["params"]["summarize_fn"] = build_llm_summarize_fn(engine)
        else:
            logger.warning(
                "working_memory.compaction.strategy=summarize needs a live LLM "
                "engine to build summaries; none available here — falling back "
                "to keep_recent (unbounded history, no compaction)."
            )
            binding = {"type": "stack", "params": {}}
    spec["context_manager"] = binding
