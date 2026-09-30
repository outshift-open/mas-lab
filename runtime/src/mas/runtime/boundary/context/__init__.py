#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Context pipeline — working memory, CMFactory-backed assembly."""

from mas.runtime.boundary.context.assemble import assemble_llm_messages, compact_committed_history
from mas.runtime.boundary.context.working_memory import SOURCE_TYPE, WorkingMemoryStore
from mas.runtime.contracts.cm_factory import CMFactory

__all__ = [
    "SOURCE_TYPE",
    "CMFactory",
    "WorkingMemoryStore",
    "assemble_llm_messages",
    "compact_committed_history",
]
