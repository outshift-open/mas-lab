#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Delegation boundary — workflow policy and peer-delegation plugins."""

from mas.runtime.boundary.delegation.llm_delegator import LlmDelegator
from mas.runtime.boundary.delegation.policy import (
    DELEGATE_TOOL_PREFIX,
    delegate_tool_name,
    delegation_targets,
    entry_agent_id,
    openai_delegation_tools,
    parse_delegate_tool_name,
    uses_llm_peer_delegation,
    workflow_type,
)
from mas.runtime.boundary.delegation.protocol import DelegationContract

__all__ = [
    "DELEGATE_TOOL_PREFIX",
    "DelegationContract",
    "LlmDelegator",
    "delegate_tool_name",
    "delegation_targets",
    "entry_agent_id",
    "openai_delegation_tools",
    "parse_delegate_tool_name",
    "uses_llm_peer_delegation",
    "workflow_type",
]
