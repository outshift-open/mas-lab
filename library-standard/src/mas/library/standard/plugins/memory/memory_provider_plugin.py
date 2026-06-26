# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Memory Provider Plugin - Abstract memory access interface.

Base plugin for memory read/write, independent of backend implementation.
Different backends (MCP, Redis, local, SQL) implement this interface.

This class extends :class:`~mas.runtime.contracts.memory_contract.MemoryContract`
so that ALL memory backends are contract-compliant and hook-observable.
The pre_memory_store / post_memory_store / pre_memory_read / post_memory_read
hooks fire automatically for any concrete provider.

Implementations:
- MCPPlugin: MCP protocol implementation (see mcp_plugin.py)
- InMemoryProvider: In-process dict (tests, single-user)
- FileSessionProvider: JSON file persistence (session memory)
- SemanticMemoryProvider: SQLite+vec vector store (semantic memory)
- RedisMemoryProvider: Redis backend
"""

from typing import Any, Dict

from mas.runtime.contracts.memory_contract import MemoryContract


class MemoryProviderPlugin(MemoryContract):
    """Base plugin for memory access — extends MemoryContract.

    All memory backends inherit from this class, which is itself a
    :class:`MemoryContract`.  This means every provider is automatically
    subject to the ``pre_memory_store`` / ``post_memory_store`` /
    ``pre_memory_read`` / ``post_memory_read`` hooks declared in the
    contract, ensuring governance, telemetry, and provenance tracking.

    Subclasses MUST implement ``read_memory()`` and ``write_memory()``.
    """

    contract_id = "memory"

    # read_memory / write_memory are inherited from MemoryContract
    # and raise NotImplementedError by default — subclasses must override.
