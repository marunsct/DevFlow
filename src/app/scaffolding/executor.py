"""Executor for project scaffolding."""

from __future__ import annotations

import os
from pathlib import Path

from app.scaffolding.registry import get_scaffold_commands
from app.tools.sandbox import SandboxExecutor


def execute_scaffolding(
    repo_root: str,
    app_name: str,
    framework: str,
) -> tuple[bool, str]:
    """Execute the scaffolding commands for the chosen framework.
    
    Returns (success, output).
    """
    commands = get_scaffold_commands(framework, app_name)
    
    # Run the main scaffolding command
    output = []
    
    # Sanitize app name
    app_name = "".join(c for c in app_name if c.isalnum() or c in ("-", "_")).lower()
    if not app_name:
        app_name = "app"
        
    try:
        res = SandboxExecutor.execute(commands["command"], repo_root=repo_root, role_name="principal_architect", category="install")
        output.append(res.get("stdout", "") + res.get("stderr", "") + res.get("error", ""))
        if str(res.get("returncode", "0")) != "0" or "error" in res:
            return False, "\n".join(output)
        
        # Run setup commands
        for cmd in commands["setup_commands"]:
            res = SandboxExecutor.execute(cmd, repo_root=repo_root, role_name="principal_architect", category="install")
            output.append(res.get("stdout", "") + res.get("stderr", "") + res.get("error", ""))
            if str(res.get("returncode", "0")) != "0" or "error" in res:
                return False, "\n".join(output)
            
        return True, "\n".join(output)
    except RuntimeError as e:
        return False, str(e)
