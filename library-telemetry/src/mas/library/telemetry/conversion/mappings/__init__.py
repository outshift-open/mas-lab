#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Native-event → OTel-span handlers, grouped by ontology block.

Each category module registers its handlers via
:func:`mas.library.telemetry.conversion.mappings.base.register`.  The converter
assembles the complete dispatch table with :func:`build_handler_table`.

Categories (mirroring the ontology blocks in
:mod:`mas.library.telemetry.conversion.envelope`):

======================  ==========================================================
Module                  Event kinds
======================  ==========================================================
``structural.py``       mas_call, execution (AgentCall), infrastructure_info
``execution.py``        llm_call, tool_call, processing_call, skill_execution,
                        network_call, workflow_transition, agent_communication
``memory.py``           memory_store / memory_read / memory_retrieve / rag_query
``context.py``          context_assembled, context_part_contributed,
                        state_update, compaction
``governance.py``       governance_event / policy / hitl / budget / control
``trajectory.py``       routing, user_input / user_output, parallel_group,
                        obs_wrap_gov
======================  ==========================================================
"""

from mas.library.telemetry.conversion.mappings.base import (
    Handler,
    SpanEmitter,
    build_handler_table,
    register,
    registered_kinds,
)

__all__ = [
    "Handler",
    "SpanEmitter",
    "register",
    "build_handler_table",
    "registered_kinds",
]
