#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Contract Executor - Runs contract tests against hook/protocol implementations.

Executes the three contract types from the MaskAT formal verification paper:
1. Hook Interception (Contract 1)
2. Protocol Validation (Contract 2)
3. Governance Enforcement (Contract 3)
"""

from typing import List, Dict, Any, Protocol, Optional
from dataclasses import dataclass, field
from enum import Enum
import time
import traceback


class ContractType(Enum):
    """Types of contracts from the formal verification paper."""
    HOOK_INTERCEPTION = "hook-interception"
    PROTOCOL_VALIDATION = "protocol"
    GOVERNANCE_ENFORCEMENT = "governance"


class TestResult(Enum):
    """Test execution outcomes."""
    PASS = "pass"
    FAIL = "fail"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result of executing a single test case."""
    test_case_index: int
    action: Dict[str, Any]
    expected: str
    actual: str
    result: TestResult
    execution_time_ms: float
    error_message: Optional[str] = None
    rationale: Optional[str] = None


@dataclass
class ContractExecutionReport:
    """Complete report of contract execution."""
    contract_name: str
    contract_type: str
    total_tests: int
    passed: int = 0
    failed: int = 0
    ambiguous: int = 0
    errors: int = 0
    execution_time_ms: float = 0.0
    test_results: List[ExecutionResult] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate pass rate (excluding ambiguous)."""
        deterministic_tests = self.total_tests - self.ambiguous
        if deterministic_tests == 0:
            return 0.0
        return (self.passed / deterministic_tests) * 100.0
    
    @property
    def compliant(self) -> bool:
        """Returns True if all non-ambiguous tests passed."""
        return self.failed == 0 and self.errors == 0


class GovernanceHookProtocol(Protocol):
    """
    Protocol for governance hook implementations.
    
    Hooks must implement this interface to be testable by Contract 3.
    """
    
    def evaluate_action(self, action: Dict[str, Any]) -> str:
        """
        Evaluate an action against the governance policy.
        
        Args:
            action: Action dict (e.g., {"type": "tool_call", "tool": "send", "args": {...}})
        
        Returns:
            "allow" or "block"
            
        Raises:
            PolicyViolation: If action violates policy (equivalent to "block")
        """
        ...


class ProtocolValidatorProtocol(Protocol):
    """
    Protocol for L8/L9 protocol validators.
    
    Validators must implement this interface to be testable by Contract 2.
    """
    
    def validate(self, message: Dict[str, Any]) -> bool:
        """
        Validate a message against the protocol schema.
        
        Args:
            message: Protocol message dict
        
        Returns:
            True if valid, False otherwise
            
        Raises:
            SchemaError: If message is malformed
        """
        ...


class ContractExecutor:
    """
    Executes contract tests against implementations.
    
    Usage:
        executor = ContractExecutor()
        
        # Test a governance hook
        from .loader import ContractLoader
        contract = ContractLoader().load("contracts/no-pii.yaml")
        report = executor.execute_governance_contract(contract, MyGovernanceHook())
        
        print(f"Compliance: {report.compliant}")
        print(f"Pass rate: {report.success_rate:.1f}%")
    """
    
    def execute_governance_contract(
        self,
        contract,  # Contract type from loader
        implementation: GovernanceHookProtocol,
        verbose: bool = False
    ) -> ContractExecutionReport:
        """
        Execute Contract 3: Governance Enforcement tests.
        
        Args:
            contract: Loaded Contract object
            implementation: Governance hook to test
            verbose: Print test progress
        
        Returns:
            Execution report with pass/fail results
        """
        report = ContractExecutionReport(
            contract_name=contract.name,
            contract_type=contract.type,
            total_tests=len(contract.test_cases)
        )
        
        start_time = time.time()
        
        for i, test_case in enumerate(contract.test_cases):
            if verbose:
                print(f"Running test {i+1}/{report.total_tests}: {test_case.rationale}")
            
            result = self._execute_governance_test(test_case, implementation)
            result.test_case_index = i
            report.test_results.append(result)
            
            # Update counters
            if result.result == TestResult.PASS:
                report.passed += 1
            elif result.result == TestResult.FAIL:
                report.failed += 1
            elif result.result == TestResult.AMBIGUOUS:
                report.ambiguous += 1
            else:  # ERROR
                report.errors += 1
        
        report.execution_time_ms = (time.time() - start_time) * 1000
        
        return report
    
    def _execute_governance_test(
        self,
        test_case,  # TestCase from loader
        implementation: GovernanceHookProtocol
    ) -> ExecutionResult:
        """Execute a single governance test case."""
        start_time = time.time()
        
        # Handle ambiguous expected outcomes
        if test_case.expected == "?":
            return ExecutionResult(
                test_case_index=-1,
                action=test_case.action,
                expected=test_case.expected,
                actual="?",
                result=TestResult.AMBIGUOUS,
                execution_time_ms=0.0,
                rationale=test_case.rationale
            )
        
        try:
            # Call the governance hook
            actual = implementation.evaluate_action(test_case.action)
            execution_time = (time.time() - start_time) * 1000
            
            # Compare expected vs actual
            if actual == test_case.expected:
                result = TestResult.PASS
                error_message = None
            else:
                result = TestResult.FAIL
                error_message = f"Expected {test_case.expected}, got {actual}"
            
            return ExecutionResult(
                test_case_index=-1,
                action=test_case.action,
                expected=test_case.expected,
                actual=actual,
                result=result,
                execution_time_ms=execution_time,
                error_message=error_message,
                rationale=test_case.rationale
            )
        
        except Exception as e:
            # Handle exceptions (e.g., PolicyViolation raised by hook)
            execution_time = (time.time() - start_time) * 1000
            
            # If exception was expected (block), it's a PASS
            # Otherwise it's an ERROR
            if test_case.expected == "block" and "PolicyViolation" in str(type(e).__name__):
                result = TestResult.PASS
                actual = "block"
                error_message = None
            else:
                result = TestResult.ERROR
                actual = "error"
                error_message = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            
            return ExecutionResult(
                test_case_index=-1,
                action=test_case.action,
                expected=test_case.expected,
                actual=actual,
                result=result,
                execution_time_ms=execution_time,
                error_message=error_message,
                rationale=test_case.rationale
            )
    
    def execute_hook_interception_contract(
        self,
        runtime_implementation: Any,
        verbose: bool = False
    ) -> ContractExecutionReport:
        """
        Execute Contract 1: Hook Interception tests.
        
        Verifies that all actions pass through hooks (no bypasses).
        
        Args:
            runtime_implementation: Runtime to test
            verbose: Print test progress
        
        Returns:
            Execution report
        """
        actions = [
            {"type": "llm_call"},
            {"type": "tool_call", "tool": "search_docs"},
            {"type": "send_response"},
        ]

        report = ContractExecutionReport(
            contract_name="hook_interception",
            contract_type=ContractType.HOOK_INTERCEPTION.value,
            total_tests=len(actions),
        )

        start_time = time.time()
        emit_action = getattr(runtime_implementation, "emit_action", None)
        hook_log = getattr(runtime_implementation, "hook_log", None)
        supports_interface = callable(emit_action) and isinstance(hook_log, list)

        for i, action in enumerate(actions):
            test_start = time.time()
            if verbose:
                print(f"Running hook test {i+1}/{report.total_tests}: {action}")

            if not supports_interface:
                result = ExecutionResult(
                    test_case_index=i,
                    action=action,
                    expected="hook_invoked",
                    actual="interface_missing",
                    result=TestResult.ERROR,
                    execution_time_ms=0.0,
                    error_message="runtime must expose emit_action(action) and hook_log list",
                    rationale="Runtime does not expose hook interception probe interface",
                )
                report.errors += 1
                report.test_results.append(result)
                continue

            try:
                before_len = len(hook_log)
                emit_action(action)
                after_log = hook_log[before_len:]
                invoked = any(entry.get("action") == action.get("type") for entry in after_log if isinstance(entry, dict))
                execution_time = (time.time() - test_start) * 1000

                if invoked:
                    report.passed += 1
                    outcome = TestResult.PASS
                    actual = "hook_invoked"
                    error_message = None
                else:
                    report.failed += 1
                    outcome = TestResult.FAIL
                    actual = "hook_missing"
                    error_message = "No hook entry recorded for action"

                report.test_results.append(ExecutionResult(
                    test_case_index=i,
                    action=action,
                    expected="hook_invoked",
                    actual=actual,
                    result=outcome,
                    execution_time_ms=execution_time,
                    error_message=error_message,
                ))
            except Exception as exc:
                report.errors += 1
                report.test_results.append(ExecutionResult(
                    test_case_index=i,
                    action=action,
                    expected="hook_invoked",
                    actual="error",
                    result=TestResult.ERROR,
                    execution_time_ms=(time.time() - test_start) * 1000,
                    error_message=f"{type(exc).__name__}: {exc}",
                ))

        report.execution_time_ms = (time.time() - start_time) * 1000
        return report
    
    def execute_protocol_validation_contract(
        self,
        protocol_validator: ProtocolValidatorProtocol,
        fuzzing_iterations: int = 1000,
        verbose: bool = False
    ) -> ContractExecutionReport:
        """
        Execute Contract 2: Protocol Validation tests.
        
        Fuzzes protocol messages to find schema violations.
        
        Args:
            protocol_validator: Validator to test
            fuzzing_iterations: Number of fuzz test cases
            verbose: Print test progress
        
        Returns:
            Execution report
        """
        valid_cases = [
            {"type": "tool_call", "payload": {"tool": "search_docs", "args": {"q": "x"}}},
            {"type": "agent_response", "payload": {"content": "ok"}},
        ]
        invalid_cases = [
            {},
            {"type": None},
            {"payload": "not-a-dict"},
        ]

        tests = [(case, True) for case in valid_cases] + [(case, False) for case in invalid_cases]
        report = ContractExecutionReport(
            contract_name="protocol_validation",
            contract_type=ContractType.PROTOCOL_VALIDATION.value,
            total_tests=len(tests),
        )

        start_time = time.time()
        for i, (message, expected) in enumerate(tests):
            if verbose:
                print(f"Running protocol test {i+1}/{report.total_tests}: {message}")
            test_start = time.time()
            try:
                actual = protocol_validator.validate(message)
                execution_time = (time.time() - test_start) * 1000
                if bool(actual) == expected:
                    outcome = TestResult.PASS
                    report.passed += 1
                    error_message = None
                else:
                    outcome = TestResult.FAIL
                    report.failed += 1
                    error_message = f"Expected {expected}, got {actual}"
                report.test_results.append(ExecutionResult(
                    test_case_index=i,
                    action=message,
                    expected=str(expected),
                    actual=str(actual),
                    result=outcome,
                    execution_time_ms=execution_time,
                    error_message=error_message,
                ))
            except Exception as exc:
                report.errors += 1
                report.test_results.append(ExecutionResult(
                    test_case_index=i,
                    action=message,
                    expected=str(expected),
                    actual="error",
                    result=TestResult.ERROR,
                    execution_time_ms=(time.time() - test_start) * 1000,
                    error_message=f"{type(exc).__name__}: {exc}",
                ))

        report.execution_time_ms = (time.time() - start_time) * 1000
        return report
