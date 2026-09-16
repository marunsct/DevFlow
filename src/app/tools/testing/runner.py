import json
import re
from pydantic import BaseModel, Field
from typing import Any, List, Optional, Sequence
from app.tools.sandbox import SandboxExecutor, _as_exit_code

class TestFailure(BaseModel):
    test_name: str = Field(..., description="Name of the failed test")
    file: Optional[str] = Field(None, description="File containing the test")
    line: Optional[int] = Field(None, description="Line number of the failure")
    message: str = Field(..., description="Error message or assertion failure")
    traceback: Optional[str] = Field(None, description="Stack trace or detailed error")

class TestResult(BaseModel):
    success: bool = Field(..., description="True if all tests passed")
    total_tests: int = Field(0, description="Total number of tests run")
    passed: int = Field(0, description="Number of passing tests")
    failed: int = Field(0, description="Number of failing tests")
    failures: List[TestFailure] = Field(default_factory=list, description="Details of failed tests")
    stdout: str = Field(..., description="Raw output from the test runner")
    stderr: str = Field(..., description="Raw error output from the test runner")

class TestRunner:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root

    def run_tests(self, command: Sequence[str], role_name: str = "general") -> TestResult:
        result = SandboxExecutor.execute(command, repo_root=self.repo_root, role_name=role_name, category="test")
        
        if "error" in result:
            return TestResult(
                success=False,
                stdout="",
                stderr=result["error"],
                failures=[TestFailure(test_name="Execution Error", message=result["error"])]
            )

        # `_as_exit_code` rather than `== "0"`. `SandboxExecutor.execute`
        # stringifies the exit code today, so the literal comparison happens to
        # work; nothing says it must, and an executor that returned an int
        # would flip every result here to "failed" in silence. This class is
        # not wired into the workflow, which is exactly why that would go
        # unnoticed.
        success = _as_exit_code(result.get("returncode")) == 0
        stdout = result["stdout"]
        stderr = result["stderr"]

        return self._parse_results(command, success, stdout, stderr)

    def _parse_results(self, command: Sequence[str], success: bool, stdout: str, stderr: str) -> TestResult:
        # Check if pytest is used and configured to output JSON report
        if "pytest" in command and "--report-log" in command:
            # We would parse the JSON report file here
            # For simplicity in this implementation, we will fallback to basic stdout parsing
            pass

        # Fallback basic parser for pytest
        failures = []
        total = 0
        passed = 0
        failed = 0
        
        combined_output = stdout + "\n" + stderr
        
        if "pytest" in command:
            # Look for summary line: e.g., "== 2 failed, 1 passed in 0.12s =="
            summary_match = re.search(r"==.*?((\d+)\s+failed)?.*?((\d+)\s+passed)?.*?==", combined_output)
            if summary_match:
                if summary_match.group(2):
                    failed = int(summary_match.group(2))
                if summary_match.group(4):
                    passed = int(summary_match.group(4))
                total = passed + failed

            # Extract FAILURES sections
            failure_blocks = re.split(r"_{3,}\s+.*?_{3,}", combined_output)
            if len(failure_blocks) > 1:
                for block in failure_blocks[1:]:
                    if not block.strip():
                        continue
                    
                    # Try to extract the failing line and error
                    lines = block.split('\n')
                    err_msg = "\n".join(lines[:5])  # First few lines as message
                    failures.append(TestFailure(
                        test_name="Pytest Failure",
                        message=err_msg.strip(),
                        traceback=block.strip()
                    ))
                    
        return TestResult(
            success=success,
            total_tests=total,
            passed=passed,
            failed=failed,
            failures=failures,
            stdout=stdout,
            stderr=stderr
        )
