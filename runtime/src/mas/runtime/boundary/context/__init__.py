#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Context pipeline — working memory, CMFactory-backed assembly."""

from mas.runtime.boundary.context.assemble import assemble_llm_messages
from mas.runtime.boundary.context.skills import inject_skills_into_context, skill_refs_from_manifest
from mas.runtime.boundary.context.trim import context_manager_spec
from mas.runtime.boundary.context.working_memory import (
    SOURCE_TYPE,
    WorkingMemoryContextSource,
    WorkingMemoryStore,
    working_memory_source,
)
from mas.runtime.contracts.cm_factory import CMFactory

__all__ = [
    "SOURCE_TYPE",
    "CMFactory",
    "WorkingMemoryContextSource",
    "WorkingMemoryStore",
    "assemble_llm_messages",
    "context_manager_spec",
    "inject_skills_into_context",
    "skill_refs_from_manifest",
    "working_memory_source",
]
