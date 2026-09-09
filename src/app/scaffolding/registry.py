"""Scaffolding Template Registry."""

from __future__ import annotations

import shlex
from typing import TypedDict


class ScaffoldingCommand(TypedDict):
    """Command to execute for scaffolding a project."""
    command: str
    setup_commands: list[str]


def get_scaffold_commands(framework: str, app_name: str) -> ScaffoldingCommand:
    """Get the scaffolding commands for a given framework.
    
    If the framework is unrecognized, defaults to a basic python project.
    """
    framework_lower = framework.lower()
    safe_name = shlex.quote(app_name)
    
    if "react" in framework_lower or "vite" in framework_lower:
        return {
            "command": f"npx create-vite {safe_name} --template react-ts",
            "setup_commands": [f"cd {safe_name} && npm install"]
        }
    elif "nest" in framework_lower:
        # NestJS CLI asks for package manager interactively by default, we force npm
        return {
            "command": f"npx @nestjs/cli new {safe_name} --package-manager npm --strict",
            "setup_commands": [] # nest cli installs deps automatically
        }
    elif "next" in framework_lower:
        return {
            "command": f"npx create-next-app@latest {safe_name} --ts --tailwind --eslint --app --src-dir --import-alias '@/*' --use-npm",
            "setup_commands": []
        }
    elif "fastapi" in framework_lower:
        return {
            "command": f"mkdir -p {safe_name}/src {safe_name}/tests",
            "setup_commands": [
                f"cd {safe_name} && uv venv",
                f"cd {safe_name} && uv pip install fastapi uvicorn pytest",
                f"echo 'from fastapi import FastAPI\\n\\napp = FastAPI()\\n\\n@app.get(\"/\")\\ndef read_root():\\n    return {{\"Hello\": \"World\"}}' > {safe_name}/src/main.py"
            ]
        }
    else:
        # Fallback to simple python module structure
        return {
            "command": f"mkdir -p {safe_name}/src {safe_name}/tests",
            "setup_commands": [
                f"cd {safe_name} && uv venv",
                f"cd {safe_name} && uv pip install pytest"
            ]
        }
