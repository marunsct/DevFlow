"""What every Python pack shares: a virtual environment and pytest with JUnit reports."""

from __future__ import annotations

#: `asyncio_mode = auto`: with pytest-asyncio installed, an `async def` test or
#: fixture runs as written. In its default strict mode each needs a marker, and
#: this file is the harness's: measured on one gate run, a service's async
#: tests failed to set up round after round ("requested an async fixture") and
#: a fixer could not change the mode. Without the plugin pytest only warns.
PYTEST_INI = """[pytest]
pythonpath = .
addopts = -p no:cacheprovider
asyncio_mode = auto
"""

GITIGNORE = """.venv/
__pycache__/
*.pyc
test-results/
data/
"""

INSTALL = (
    ("python3", "-m", "venv", ".venv"),
    (".venv/bin/python", "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
     "-r", "requirements.txt", "-r", "requirements-dev.txt"),
)

#: The Python version the harness's own image runs, so CI tests the product on
#: the runtime it was built and tested on.
PYTHON_VERSION = "3.12"

CI_SETUP = (
    "      - uses: actions/setup-python@v5\n"
    "        with:\n"
    f'          python-version: "{PYTHON_VERSION}"',
)

DOCKERIGNORE = """.venv/
__pycache__/
*.pyc
test-results/
data/
tests/
acceptance/
.git/
"""


def service_dockerfile(server: str, port: int = 8000) -> str:
    """A container for a Python service; `server` is the command after `python -m`.

    Requirements are installed before the source is copied, so a change to the
    code does not reinstall them; it runs as an unprivileged user; and it
    listens on every interface (`HOST`), which inside a container is the only
    way anything reaches it. Configuration comes from the environment the
    service already reads - `PORT`, `DATA_DIR` - never a credential written
    into the file.
    """
    return (
        "# {{title}}: build with `docker build -t {{project}} .`, run with\n"
        f"# `docker run -p {port}:{port} -v {{{{project}}}}-data:/app/data {{{{project}}}}`.\n"
        f"FROM python:{PYTHON_VERSION}-slim\n"
        f"ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT={port} DATA_DIR=/app/data\n"
        "WORKDIR /app\n"
        "COPY requirements.txt ./\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n"
        "COPY . .\n"
        "RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app:app /app/data\n"
        "USER app\n"
        f"EXPOSE {port}\n"
        f'CMD ["sh", "-c", "exec python -m {server} --host \\"$HOST\\" --port \\"$PORT\\""]\n'
    )


UNIT_TEST = (".venv/bin/python", "-m", "pytest", "tests", "-q", "--junitxml=test-results/unit.xml")
ACCEPTANCE_TEST = (
    ".venv/bin/python", "-m", "pytest", "acceptance", "-q", "--junitxml=test-results/acceptance.xml",
)

UNIT_GUIDE = """Unit tests go in `tests/`, named `test_<module>.py`, as plain pytest functions
that import the product's modules directly (`from {{package}}.<module> import ...`).
Install a new dependency by adding it to `requirements.txt` (or
`requirements-dev.txt` for test-only tools) and running
`.venv/bin/python -m pip install -r requirements.txt`. Run the unit tests with
`.venv/bin/python -m pytest tests`. Never start a server yourself. Anything a test opens
is closed when the tests end: an async database engine is made inside a fixture that
yields it and then awaits `engine.dispose()` (use `NullPool` for a test database), never at
import time - a thread left open keeps pytest alive after it has printed its results."""

#: How an acceptance test names the criterion it proves. Python test names are
#: identifiers, so the id is written into the function name.
NAMING = """Name each test after the criterion it proves: `test_ac3_<what_it_checks>` for
AC-3 (a test that proves two writes both: `test_ac3_ac4_<...>`). A test with no
criterion id in its name proves nothing the harness can count."""


#: A pytest failure raised by the test's own code: a name it never defined, a
#: fixture that does not exist, a file that does not parse. An ImportError or
#: AttributeError is left out: before anything is built, the product's module
#: or function not existing yet is exactly what a test should fail on.
#: The unit test files pytest collects by default, and where its fixtures live.
UNIT_TEST_NAMES = ("test_*.py", "*_test.py")
TEST_HELPERS = ("conftest.py",)

TEST_BUGS = (
    r"\bNameError\b",
    r"\b(?:SyntaxError|IndentationError)\b",
    r"fixture '[^']+' not found",
)
