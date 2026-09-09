from pathlib import Path
from app.models import TechnologyStack
import os
from jinja2 import Template

CI_TEMPLATE = """\
name: CI

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
{% if lang in ('python', 'python3') %}
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Install uv
      run: curl -LsSf https://astral.sh/uv/install.sh | sh
    - name: Install dependencies
      run: |
        uv pip install --system -r requirements.txt
        uv pip install --system pytest ruff
    - name: Lint with ruff
      run: ruff check .
    - name: Test with pytest
      run: pytest
{% elif lang in ('typescript', 'javascript', 'node') %}
    - name: Use Node.js
      uses: actions/setup-node@v4
      with:
        node-version: "20.x"
    - run: npm ci
    - run: npm run build --if-present
    - run: npm test
{% elif lang in ('go', 'golang') %}
    - name: Set up Go
      uses: actions/setup-go@v5
      with:
        go-version: '1.22'
    - name: Build
      run: go build -v ./...
    - name: Test
      run: go test -v ./...
{% elif lang in ('java', 'kotlin') %}
    - name: Set up JDK 21
      uses: actions/setup-java@v4
      with:
        java-version: '21'
        distribution: 'temurin'
    - name: Build with Maven
      run: mvn -B package --file pom.xml
{% else %}
    - name: Run checks
      run: echo "No automated CI steps defined for this language"
{% endif %}
"""

class CIGenerator:
    def __init__(self, repo_root: str, stack: TechnologyStack):
        self.repo_root = Path(repo_root)
        self.stack = stack

    def generate(self) -> None:
        """
        Generate a GitHub Actions CI pipeline for the project.
        """
        os.makedirs(self.repo_root / ".github" / "workflows", exist_ok=True)
        
        lang = self.stack.language.lower()
        template = Template(CI_TEMPLATE)
        ci_content = template.render(lang=lang)

        with open(self.repo_root / ".github" / "workflows" / "ci.yml", "w") as f:
            f.write(ci_content)
