#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Manifest-aligned defaults — values originate in JSON Schema (see gen_schema_artifacts)."""

from __future__ import annotations

from mas.runtime.spec.schema_defaults_generated import (
    CONTEXT_MANAGER_RESERVE_TOKENS,
    CONTEXT_MANAGER_WORKING_MEMORY_MESSAGES,
    EXECUTION_ENGINE_QUEUE_DEPTH,
    EXECUTION_MAX_AUTO_STEPS,
)

# Execution (spec.execution)
DEFAULT_MAX_AUTO_STEPS = EXECUTION_MAX_AUTO_STEPS
DEFAULT_ENGINE_QUEUE_DEPTH = EXECUTION_ENGINE_QUEUE_DEPTH

# Context assembly (spec.context_manager.params assembly fragment)
DEFAULT_WORKING_MEMORY_MESSAGES = CONTEXT_MANAGER_WORKING_MEMORY_MESSAGES
DEFAULT_CONTEXT_RESERVE_TOKENS = CONTEXT_MANAGER_RESERVE_TOKENS

__all__ = [
    "DEFAULT_CONTEXT_RESERVE_TOKENS",
    "DEFAULT_ENGINE_QUEUE_DEPTH",
    "DEFAULT_MAX_AUTO_STEPS",
    "DEFAULT_WORKING_MEMORY_MESSAGES",
    "CONTEXT_MANAGER_RESERVE_TOKENS",
    "CONTEXT_MANAGER_WORKING_MEMORY_MESSAGES",
    "EXECUTION_ENGINE_QUEUE_DEPTH",
    "EXECUTION_MAX_AUTO_STEPS",
]
