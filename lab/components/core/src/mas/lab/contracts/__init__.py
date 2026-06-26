#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Contract testing framework for Agent-Runtime implementations.

This module provides formal contract testing capabilities to verify that
agent implementations satisfy the theoretical guarantees of Theorem 1 and 2
from the MaskAT formal verification paper.

The framework consists of:
- ContractLoader: Loads YAML contract specifications
- TestGenerator: Automatically generates test cases from formal policies
- ContractExecutor: Runs tests against hook/protocol implementations
- ComplianceReporter: Generates structured pass/fail reports

Usage:
    from mas.lab.contracts import ContractExecutor
    
    executor = ContractExecutor()
    results = executor.run_contract_tests(
        contract_path="contracts/no-pii-leakage.yaml",
        implementation=MyGovernanceHook()
    )
    
    print(results.summary())
"""

from .loader import ContractLoader
from .generator import TestGenerator
from .executor import ContractExecutor
from .reporter import ComplianceReporter
from .controller import (
    AgentSnapshot,
    ControllerContract,
    DeployResult,
    InfraSnapshot,
    discover_controllers,
    get_controller,
)

__all__ = [
    "ContractLoader",
    "TestGenerator",
    "ContractExecutor",
    "ComplianceReporter",
    "ControllerContract",
    "InfraSnapshot",
    "AgentSnapshot",
    "DeployResult",
    "discover_controllers",
    "get_controller",
]
