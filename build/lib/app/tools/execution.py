import subprocess
from langchain_core.tools import tool
import os
import re

def _run_cmd(command: str, cwd: str) -> dict[str, str]:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": str(result.returncode)
        }
    except Exception as exc:
        return {"error": str(exc)}

def get_execution_tools(repo_root: str):
    """Factory for execution tools bound to a specific repository."""
    
    @tool
    def scaffold_project(command: str, project_name: str) -> dict[str, str]:
        """Scaffold a new project using arbitrary CLI frameworks.
        
        Args:
            command: The exact setup command to run (e.g. 'npx create-next-app@latest my-app', 'django-admin startproject my_project .')
            project_name: The name of the project directory to create
        """
        cwd = repo_root
        
        # Security allowlist for scaffolding commands
        if not re.match(r"^(npx create-|npm create |yarn create |pnpm create |python -m venv|pip install|django-admin startproject|cargo new|vue create|ng new)", command):
            return {"error": "Invalid scaffold command. Must use standard framework scaffolding tools."}
            
        os.makedirs(os.path.join(cwd, project_name), exist_ok=True)
        # If the command doesn't create the directory itself, we might want to run it inside the directory
        # We will just run it from repo_root since `npx create-*` usually expects to create the folder.
        
        return _run_cmd(command, cwd)

    @tool
    def install_dependencies(project_path: str, package_manager: str = "npm") -> dict[str, str]:
        """Install dependencies for a project.
        
        Args:
            project_path: Relative path to the project directory from repo root.
            package_manager: 'npm', 'yarn', 'pnpm', or 'pip'
        """
        cwd = os.path.join(repo_root, project_path)
        if not os.path.exists(cwd):
            return {"error": f"Path {cwd} does not exist."}
            
        if package_manager in ['npm', 'yarn', 'pnpm']:
            cmd = f"{package_manager} install"
        elif package_manager == 'pip':
            cmd = "pip install -r requirements.txt"
        else:
            return {"error": f"Package manager {package_manager} is not supported."}
            
        return _run_cmd(cmd, cwd)
        
    @tool
    def execute_tests(project_path: str, test_command: str) -> dict[str, str]:
        """Execute automated tests and return the results.
        
        Args:
            project_path: Relative path to the project directory.
            test_command: The command to run (e.g., 'npm test', 'pytest')
        """
        cwd = os.path.join(repo_root, project_path)
        if not os.path.exists(cwd):
            return {"error": f"Path {cwd} does not exist."}
            
        # Allowlist for test commands
        if not re.match(r"^(npm|yarn|pnpm|pytest|python -m pytest)", test_command):
            return {"error": "Invalid test command. Must use standard testing frameworks."}
            
        return _run_cmd(test_command, cwd)

    return [scaffold_project, install_dependencies, execute_tests]
