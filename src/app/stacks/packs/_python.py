"""What every Python pack shares: a virtual environment and pytest with JUnit reports."""

from __future__ import annotations

PYTEST_INI = """[pytest]
pythonpath = .
addopts = -p no:cacheprovider
timeout = 90
"""

#: A test may run this long before it fails on its own (`pytest-timeout`, in
#: each pack's `requirements-dev.txt`). Without one, a test that starts the
#: product and waits for it - `subprocess.run(["bash", "start.sh"])` - never
#: returned, and the whole suite hung to the command's 300-second limit with no
#: result for any test: measured on one run's acceptance suite. Now that test
#: fails alone, says why, and every other test reports.
PER_TEST_TIMEOUT = "pytest-timeout>=2"

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
    # A request to an address the suite never serves (see the JavaScript packs').
    r"host='(?:localhost|127\.0\.0\.1|::1)', port=(?:80|443)\)",
    # A dict, list or set used as a key or set member: `json={{"title": ""}}` (a set holding a dict, double braces
    # carried over from a template), raised by the test's own line before any request is made. Measured on a
    # small-model run: five locked tests carried it, none could pass, and the sprint spent two hours on them.
    r"TypeError: unhashable type: '(?:dict|list|set)'",
)


#: Errors a Python run is known to raise, by a phrase of the message, and their cause (`app.stacks.known_errors`).
#: Measured on three held-out runs: the unit tests and the code they test disagreed about a function's parameters
#: (some tests passed a connection first, others by keyword; the product's own caller passed neither), written by
#: different work orders. Each fix changed the function to suit some tests, broke the rest and was reverted, and the
#: sprint was planned again until the run failed.
PYTHON_KNOWN_ERRORS = {
    phrase: (
        "a call and the function it calls disagree on the function's parameters - here the calls are in the unit "
        "tests and the function is in the product, written by different work orders. Read how the product's own code "
        "calls the function, call it that way in every test of the file in one rewrite of the file, and change the "
        "function only when the product's own callers need it. Changing the function to suit some tests breaks the "
        "rest."
    )
    for phrase in ("positional argument", "unexpected keyword argument")
}
#: Measured on a held-out run: unit tests used the product's database helper in a `with` block while the product
#: defines it as a plain generator it hands to a framework as a dependency; each fix changed the helper to suit some
#: tests, broke the rest and was reverted.
PYTHON_KNOWN_ERRORS["context manager protocol"] = (
    "the unit tests use a function in a `with` block, but the product defines it as a plain generator (it hands it to "
    "a framework as a dependency, or iterates it). Read how the product's own code uses the function and keep that "
    "definition: change the TESTS - call the generator with `next(...)` and close it, or wrap it with "
    "`contextlib.contextmanager` inside the test module - in every test of the file in one rewrite. Changing the "
    "product's function to suit some tests breaks its other callers."
)
