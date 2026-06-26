#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Governance action algebra — mirrors TLA GovernanceActions and mas-lab policy_engine."""

from __future__ import annotations

from enum import Enum


class GovernanceAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    TERMINATE = "TERMINATE"
    HITL = "HITL"
    LOG = "LOG"
    MODIFY = "MODIFY"
    SKIP = "SKIP"
    RETRY = "RETRY"
    BLACKLIST = "BLACKLIST"


class GovPolicyProfile(str, Enum):
    PERMISSIVE = "PERMISSIVE"
    BLOCK_DESTRUCTIVE = "BLOCK_DESTRUCTIVE"
    HITL_DESTRUCTIVE = "HITL_DESTRUCTIVE"
    LOG_ALL = "LOG_ALL"
    MODIFY_DESTRUCTIVE = "MODIFY_DESTRUCTIVE"
    TERMINATE_DESTRUCTIVE = "TERMINATE_DESTRUCTIVE"
    SKIP_DESTRUCTIVE = "SKIP_DESTRUCTIVE"
    BLACKLIST_DESTRUCTIVE = "BLACKLIST_DESTRUCTIVE"
    RETRY_DESTRUCTIVE = "RETRY_DESTRUCTIVE"


class GovIngressProfile(str, Enum):
    PERMISSIVE = "PERMISSIVE"
    RETRY_ON_ERROR = "RETRY_ON_ERROR"
    BLOCK_ON_ERROR = "BLOCK_ON_ERROR"
    SKIP_ON_ERROR = "SKIP_ON_ERROR"
