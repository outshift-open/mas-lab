#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
MaskAT Verification Framework

This module implements the contract testing framework from the MaskAT formal 
verification paper. It provides executable specifications for:

- Contract 1: Hook Interception Coverage
- Contract 2: Protocol Validation (Schema Enforcement)
- Contract 3: Governance Enforcement (Policy Correctness)

The framework bridges formal theory (Theorems 1-2 in the paper) with production
code by enabling teams to verify implementations satisfy theoretical assumptions.

Usage:
    from mas.lab.verification.contracts import ContractLoader, ContractExecutor
    
    loader = ContractLoader()
    contract = loader.load("path/to/contract.yaml")
    
    executor = ContractExecutor()
    report = executor.execute_governance_contract(contract, MyHook())
"""

from .contracts.loader import ContractLoader, Contract, TestCase
from .contracts.generator import TestGenerator
from .contracts.executor import ContractExecutor, ContractExecutionReport
from .contracts.reporter import ComplianceReporter

__all__ = [
    "ContractLoader",
    "Contract",
    "TestCase",
    "TestGenerator",
    "ContractExecutor",
    "ContractExecutionReport",
    "ComplianceReporter",
]
