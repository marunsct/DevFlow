"""An HTTP service in Python, on Flask."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _python
from app.stacks.packs import python_http_api as fastapi

REQUIREMENTS = """flask>=3.1
gunicorn>=23
"""

APP = '''"""The service's HTTP interface."""

from flask import Flask, jsonify


def create_app() -> Flask:
    """Builds the service. `wsgi.py` serves it; unit tests call it directly."""
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app
'''

WSGI = '''"""What a server runs: `gunicorn {{package}}.wsgi:app`."""

from {{package}}.app import create_app

app = create_app()
'''

#: The acceptance suite's service: the same conftest as the FastAPI pack's,
#: started by Flask's own server instead of uvicorn.
CONFTEST = fastapi.CONFTEST.replace(
    '[sys.executable, "-m", "uvicorn", "{{package}}.main:app",\n'
    '             "--host", "127.0.0.1", "--port", str(self.port)]',
    '[sys.executable, "-m", "flask", "--app", "{{package}}.app:create_app", "run",\n'
    '             "--host", "127.0.0.1", "--port", str(self.port)]',
)
assert CONFTEST != fastapi.CONFTEST, "the FastAPI conftest no longer starts the service the way this replaces"

START = """#!/bin/sh
cd "$(dirname "$0")" && exec .venv/bin/python -m gunicorn {{package}}.wsgi:app --bind "${HOST:-127.0.0.1}:${PORT:-8000}"
"""

SMOKE_UNIT = '''from {{package}}.app import create_app


def test_the_service_reports_its_health():
    assert create_app().test_client().get("/health").get_json() == {"status": "ok"}
'''

GUIDE = _python.UNIT_GUIDE + """
The application is built by `create_app()` in `{{package}}/app.py`; add routes there or
in blueprints it registers. A service that stores data keeps it under the directory in
the `DATA_DIR` environment variable (default `data/`), never in memory only. A unit
test calls routes through `create_app().test_client()`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8000:8000 -v {{project}}-data:/app/data {{project}}`.
FROM python:%(python)s-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app:app /app/data
USER app
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn {{package}}.wsgi:app --bind \\"$HOST:$PORT\\""]
""" % {"python": _python.PYTHON_VERSION}

PACK = StackPack(
    name="python-flask-api",
    title="HTTP service in Python on Flask",
    kind="http_api",
    language="python",
    frameworks=("flask",),
    files={
        "requirements.txt": REQUIREMENTS,
        "requirements-dev.txt": fastapi.REQUIREMENTS_DEV,
        "pytest.ini": _python.PYTEST_INI,
        ".gitignore": _python.GITIGNORE,
        "{{package}}/__init__.py": '"""{{title}}."""\n',
        "{{package}}/app.py": APP,
        "{{package}}/wsgi.py": WSGI,
        "acceptance/conftest.py": CONFTEST,
        "start.sh": START,
    },
    install=_python.INSTALL,
    unit_test=_python.UNIT_TEST,
    acceptance_test=_python.ACCEPTANCE_TEST,
    unit_report="test-results/unit.xml",
    acceptance_report="test-results/acceptance.xml",
    unit_dir="tests",
    acceptance_dir="acceptance",
    acceptance_pattern="test_*.py",
    unit_pattern="test_*.py",
    entrypoint="{{package}}/app.py",
    unit_test_names=_python.UNIT_TEST_NAMES,
    test_helpers=_python.TEST_HELPERS,
    kept_files=("pytest.ini", "acceptance/conftest.py"),
    kept_scripts={},
    smoke_files={
        "tests/test_scaffold_smoke.py": SMOKE_UNIT,
        "acceptance/test_scaffold_smoke.py": fastapi.SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=fastapi.ACCEPTANCE_GUIDE,
    stack={
        "language": "Python",
        "framework": "Flask",
        "frontend_framework": "",
        "testing_framework": "pytest for unit tests, pytest with httpx against the running service for acceptance tests",
    },
    check_families=frozenset({"python"}),
    test_bugs=_python.TEST_BUGS,
    ci_setup=_python.CI_SETUP,
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": _python.DOCKERIGNORE},
)
