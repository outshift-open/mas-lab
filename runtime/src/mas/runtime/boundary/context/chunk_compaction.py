#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Commit-time chunk compaction — runs after turn commit, not on every assembly."""

from __future__ import annotations

from mas.runtime.boundary.context.conversation_chunks import ConversationChunkStore
from mas.runtime.boundary.context.working_memory_compaction import WorkingMemoryCompactionRuntime


def maybe_compact_chunks_after_commit(
    store: ConversationChunkStore,
    *,
    compaction: WorkingMemoryCompactionRuntime | None,
) -> bool:
    if compaction is None:
        return False
    return store.maybe_compact(
        summary_threshold=compaction.summary_threshold,
        keep_message_chunks=compaction.keep_turns,
        summarize_fn=compaction.summarize_fn,
    )
