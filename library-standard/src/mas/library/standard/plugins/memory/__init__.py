#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Semantic memory plugins for paper labs and tutorials."""

from mas.library.standard.plugins.memory.memory_provider_plugin import MemoryProviderPlugin
from mas.library.standard.plugins.memory.memory_semantic import (
    DEFAULT_CACHE_MAX_ENTRIES,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_TOKENS,
    DEFAULT_HYBRID_TEXT_WEIGHT,
    DEFAULT_HYBRID_VECTOR_WEIGHT,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_SCORE,
    DEFAULT_MMR_LAMBDA,
    DEFAULT_TEMPORAL_DECAY_HALF_LIFE_DAYS,
    SemanticMemoryPlugin,
)

__all__ = [
    "DEFAULT_CACHE_MAX_ENTRIES",
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_TOKENS",
    "DEFAULT_HYBRID_TEXT_WEIGHT",
    "DEFAULT_HYBRID_VECTOR_WEIGHT",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_MIN_SCORE",
    "DEFAULT_MMR_LAMBDA",
    "DEFAULT_TEMPORAL_DECAY_HALF_LIFE_DAYS",
    "MemoryProviderPlugin",
    "SemanticMemoryPlugin",
]
