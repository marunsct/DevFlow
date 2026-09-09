from typing import List, Dict, Any
import os
from pathlib import Path
from pydantic import BaseModel
from app.tools.sandbox import SandboxExecutor

class DependencyConflict(Exception):
    pass


_ROLE_FOR_LANGUAGE = {
    "python": "backend_specialist",
    "python3": "backend_specialist",
    "go": "backend_specialist",
    "golang": "backend_specialist",
    "typescript": "ui_specialist",
    "javascript": "ui_specialist",
    "node": "ui_specialist",
}


class DependencyManager:
    """Resolves a project's dependencies through the contained executor.

    This used to use a second, separate SandboxExecutor that applied no
    allowlist and none of the isolation flags. There is now one executor.
    """

    def __init__(self, repo_root: str, language: str):
        self.repo_root = Path(repo_root)
        self.language = language
        self.role_name = _ROLE_FOR_LANGUAGE.get(language.lower(), "backend_specialist")
        
    def check_conflicts(self, dependencies: List[str]) -> bool:
        """
        Check for conflicts in a proposed list of dependencies based on a compatibility matrix.
        """
        # In a real system, this would consult a compatibility_matrix.yaml
        # For now, we stub it to allow all.
        return True
        
    def resolve_dependencies(self):
        """
        Runs the appropriate package manager to resolve dependencies and generate a lock file.
        """
        lang = self.language.lower()
        if lang in ("python", "python3"):
            if (self.repo_root / "requirements.txt").exists():
                self._run_command(["pip", "install", "-r", "requirements.txt"])
        elif lang in ("typescript", "javascript", "node"):
            if (self.repo_root / "package.json").exists():
                self._run_command(["npm", "install"])
        elif lang in ("go", "golang"):
            if (self.repo_root / "go.mod").exists():
                self._run_command(["go", "mod", "tidy"])
        elif lang in ("java", "kotlin"):
            if (self.repo_root / "pom.xml").exists():
                self._run_command(["mvn", "dependency:resolve"])
            elif (self.repo_root / "build.gradle").exists() or (self.repo_root / "build.gradle.kts").exists():
                self._run_command(["./gradlew", "dependencies"])
                
    def _run_command(self, cmd: List[str]) -> None:
        result = SandboxExecutor.execute(
            command=cmd,
            repo_root=str(self.repo_root),
            role_name=self.role_name,
            category="install",
        )
        if "error" in result:
            raise DependencyConflict(f"Could not resolve dependencies: {result['error']}")
        if result.get("returncode") not in ("0", 0):
            raise DependencyConflict(
                f"Dependency resolution failed: {result.get('stderr') or result.get('stdout')}"
            )
