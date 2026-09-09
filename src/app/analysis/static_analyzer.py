from pydantic import BaseModel, Field
from typing import List, Optional
from app.tools.sandbox import SandboxExecutor
import re

class AnalysisIssue(BaseModel):
    file: str = Field(..., description="File containing the issue")
    line: Optional[int] = Field(None, description="Line number of the issue")
    severity: str = Field(..., description="Severity (error, warning, info)")
    message: str = Field(..., description="Description of the issue")
    rule_id: Optional[str] = Field(None, description="Linter rule ID")

class AnalysisResult(BaseModel):
    success: bool = Field(..., description="True if no severe issues found")
    issues: List[AnalysisIssue] = Field(default_factory=list, description="List of static analysis issues")
    stdout: str = Field(..., description="Raw standard output")
    stderr: str = Field(..., description="Raw standard error")

class StaticAnalyzer:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root

    def analyze(self, command: str, role_name: str = "general") -> AnalysisResult:
        result = SandboxExecutor.execute(command, repo_root=self.repo_root, role_name=role_name, category="build")
        
        if "error" in result:
            return AnalysisResult(
                success=False,
                stdout="",
                stderr=result["error"],
                issues=[AnalysisIssue(file="Unknown", severity="error", message=result["error"])]
            )

        success = result["returncode"] == "0"
        stdout = result["stdout"]
        stderr = result["stderr"]

        issues = self._parse_issues(command, stdout, stderr)

        return AnalysisResult(
            success=success,
            issues=issues,
            stdout=stdout,
            stderr=stderr
        )

    def _parse_issues(self, command: str, stdout: str, stderr: str) -> List[AnalysisIssue]:
        issues = []
        combined = stdout + "\n" + stderr
        
        # Parse ruff/flake8 output (file.py:line:col: error_code message)
        if "ruff" in command or "flake8" in command:
            pattern = re.compile(r"^([^:]+\.py):(\d+):(?:\d+:)?\s*([A-Z]\d+)\s*(.*)$", re.MULTILINE)
            for match in pattern.finditer(combined):
                issues.append(AnalysisIssue(
                    file=match.group(1),
                    line=int(match.group(2)),
                    severity="warning" if match.group(3).startswith("W") else "error",
                    rule_id=match.group(3),
                    message=match.group(4).strip()
                ))
        
        # Parse eslint output
        elif "eslint" in command:
            # basic format: /path/to/file.js\n  line:col  error  message  rule-id
            pattern = re.compile(r"^\s*(\d+):\d+\s+(error|warning)\s+(.*?)\s+([a-z\-]+)$", re.MULTILINE)
            for match in pattern.finditer(combined):
                issues.append(AnalysisIssue(
                    file="Parsed from ESLint output",  # would need more context state to track file
                    line=int(match.group(1)),
                    severity=match.group(2),
                    rule_id=match.group(4),
                    message=match.group(3).strip()
                ))

        return issues
