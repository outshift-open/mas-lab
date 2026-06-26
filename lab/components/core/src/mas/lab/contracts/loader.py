#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Contract Loader - Parses YAML contract specifications into executable tests.

Implements the contract file format specification from Section "Contract Specification Format"
of the MaskAT formal verification paper.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class TestCase:
    """Represents a single test case from a contract."""
    action: Dict[str, Any]
    expected: str  # "allow" or "block"
    rationale: Optional[str] = None


@dataclass
class FuzzingConfig:
    """Configuration for automatic test fuzzing."""
    enabled: bool = False
    mutations: List[str] = None
    iterations: int = 1000
    
    def __post_init__(self):
        if self.mutations is None:
            self.mutations = []


@dataclass
class Contract:
    """Represents a complete contract specification."""
    name: str
    type: str  # "governance", "hook-interception", "protocol"
    policy: Dict[str, str]  # description + formal spec
    test_cases: List[TestCase]
    fuzzing: FuzzingConfig


class ContractLoader:
    """
    Loads and parses contract YAML files.
    
    Example contract file structure:
        contract:
          name: "No PII Leakage"
          type: "governance"
          policy:
            description: "Agent must never output PII"
            formal: "forall message m: contains_pii(m) => block(m)"
          test_cases:
            - action: {...}
              expected: "allow"
              rationale: "..."
          fuzzing:
            enabled: true
            mutations: ["case_variations", "spacing"]
            iterations: 1000
    """
    
    def load(self, contract_path: Path) -> Contract:
        """
        Load a contract from a YAML file.
        
        Args:
            contract_path: Path to the YAML contract file
            
        Returns:
            Parsed Contract object
            
        Raises:
            ValueError: If contract format is invalid
            FileNotFoundError: If contract file doesn't exist
        """
        if not contract_path.exists():
            raise FileNotFoundError(f"Contract file not found: {contract_path}")
        
        with open(contract_path, 'r') as f:
            data = yaml.safe_load(f)
        
        if 'contract' not in data:
            raise ValueError(f"Invalid contract format: missing 'contract' key")
        
        contract_data = data['contract']
        
        # Parse test cases
        test_cases = []
        for tc in contract_data.get('test_cases', []):
            test_cases.append(TestCase(
                action=tc['action'],
                expected=tc['expected'],
                rationale=tc.get('rationale')
            ))
        
        # Parse fuzzing config
        fuzzing_data = contract_data.get('fuzzing', {})
        fuzzing = FuzzingConfig(
            enabled=fuzzing_data.get('enabled', False),
            mutations=fuzzing_data.get('mutations', []),
            iterations=fuzzing_data.get('iterations', 1000)
        )
        
        return Contract(
            name=contract_data['name'],
            type=contract_data['type'],
            policy=contract_data['policy'],
            test_cases=test_cases,
            fuzzing=fuzzing
        )
    
    def load_batch(self, contract_pattern: str) -> List[Contract]:
        """
        Load multiple contracts matching a glob pattern.
        
        Args:
            contract_pattern: Glob pattern (e.g., "contracts/*.yaml")
            
        Returns:
            List of loaded Contract objects
        """
        from glob import glob
        
        contracts = []
        for path in glob(contract_pattern):
            contracts.append(self.load(Path(path)))
        
        return contracts
