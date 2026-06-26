#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Compliance Reporter - Generates structured pass/fail reports.

Outputs compliance reports in multiple formats for CI/CD integration
and formal verification auditing.
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from .executor import ContractExecutionReport, TestResult


class ComplianceReporter:
    """
    Generates compliance reports from contract execution results.
    
    Supports multiple output formats:
    - JSON: Machine-readable for CI/CD
    - Markdown: Human-readable for documentation
    - Console: Terminal output for interactive use
    """
    
    def generate_json_report(
        self,
        reports: List[ContractExecutionReport],
        output_path: Path
    ) -> None:
        """
        Generate a JSON compliance report.
        
        Args:
            reports: List of contract execution reports
            output_path: Where to write the JSON file
        """
        data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_contracts": len(reports),
                "compliant_contracts": sum(1 for r in reports if r.compliant),
                "total_tests": sum(r.total_tests for r in reports),
                "passed": sum(r.passed for r in reports),
                "failed": sum(r.failed for r in reports),
                "errors": sum(r.errors for r in reports),
                "ambiguous": sum(r.ambiguous for r in reports),
            },
            "contracts": [self._report_to_dict(r) for r in reports]
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def generate_markdown_report(
        self,
        reports: List[ContractExecutionReport],
        output_path: Path
    ) -> None:
        """
        Generate a Markdown compliance report.
        
        Args:
            reports: List of contract execution reports
            output_path: Where to write the Markdown file
        """
        lines = [
            "# Contract Compliance Report",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            "",
        ]
        
        # Summary table
        total_contracts = len(reports)
        compliant = sum(1 for r in reports if r.compliant)
        total_tests = sum(r.total_tests for r in reports)
        passed = sum(r.passed for r in reports)
        failed = sum(r.failed for r in reports
)
        
        lines.extend([
            f"- **Total Contracts**: {total_contracts}",
            f"- **Compliant**: {compliant} / {total_contracts}",
            f"- **Overall Pass Rate**: {(passed/total_tests*100) if total_tests > 0 else 0:.1f}%",
            "",
            "## Contract Results",
            "",
        ])
        
        # Individual contracts
        for report in reports:
            status_icon = "✅" if report.compliant else "❌"
            lines.extend([
                f"### {status_icon} {report.contract_name}",
                "",
                f"- **Type**: {report.contract_type}",
                f"- **Tests**: {report.passed} / {report.total_tests} passed",
                f"- **Failed**: {report.failed}",
                f"- **Errors**: {report.errors}",
                f"- **Execution Time**: {report.execution_time_ms:.2f} ms",
                "",
            ])
            
            # Failed tests details
            if report.failed > 0:
                lines.append("#### Failed Tests")
                lines.append("")
                for result in report.test_results:
                    if result.result == TestResult.FAIL:
                        lines.append(f"- **Test {result.test_case_index + 1}**: {result.rationale}")
                        lines.append(f"  - Expected: `{result.expected}`")
                        lines.append(f"  - Actual: `{result.actual}`")
                        if result.error_message:
                            lines.append(f"  - Error: {result.error_message}")
                        lines.append("")
        
        with open(output_path, 'w') as f:
            f.write("\n".join(lines))
    
    def print_console_summary(
        self,
        reports: List[ContractExecutionReport],
        verbose: bool = False
    ) -> None:
        """
        Print a console summary of compliance reports.
        
        Args:
            reports: List of contract execution reports
            verbose: Show detailed test results
        """
        print("\n" + "="*60)
        print("CONTRACT COMPLIANCE REPORT")
        print("="*60)
        print()
        
        # Summary
        total_contracts = len(reports)
        compliant = sum(1 for r in reports if r.compliant)
        total_tests = sum(r.total_tests for r in reports)
        passed = sum(r.passed for r in reports)
        failed = sum(r.failed for r in reports)
        
        print(f"Total Contracts: {total_contracts}")
        print(f"Compliant:       {compliant} / {total_contracts}")
        print(f"Overall Pass Rate: {(passed/total_tests*100) if total_tests > 0 else 0:.1f}%")
        print()
        
        # Individual contracts
        for report in reports:
            status = "✅ PASS" if report.compliant else "❌ FAIL"
            print(f"{status} {report.contract_name}")
            print(f"    Tests: {report.passed}/{report.total_tests} passed")
            
            if report.failed > 0:
                print(f"    Failed: {report.failed}")
                if verbose:
                    for result in report.test_results:
                        if result.result == TestResult.FAIL:
                            print(f"      - Test {result.test_case_index + 1}: {result.rationale}")
                            print(f"        Expected: {result.expected}, Got: {result.actual}")
            
            if report.errors > 0:
                print(f"    Errors: {report.errors}")
            
            print()
        
        print("="*60)
    
    def _report_to_dict(self, report: ContractExecutionReport) -> Dict[str, Any]:
        """Convert a report to a dict for JSON serialization."""
        return {
            "contract_name": report.contract_name,
            "contract_type": report.contract_type,
            "compliant": report.compliant,
            "summary": {
                "total": report.total_tests,
                "passed": report.passed,
                "failed": report.failed,
                "errors": report.errors,
                "ambiguous": report.ambiguous,
                "success_rate": report.success_rate,
                "execution_time_ms": report.execution_time_ms,
            },
            "test_results": [
                {
                    "index": r.test_case_index,
                    "action": r.action,
                    "expected": r.expected,
                    "actual": r.actual,
                    "result": r.result.value,
                    "execution_time_ms": r.execution_time_ms,
                    "error_message": r.error_message,
                    "rationale": r.rationale,
                }
                for r in report.test_results
            ]
        }
