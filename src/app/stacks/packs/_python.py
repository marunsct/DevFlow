"""What every Python pack shares: a virtual environment and pytest with JUnit reports."""

from __future__ import annotations

PYTEST_INI = """[pytest]
pythonpath = .
addopts = -p no:cacheprovider
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

UNIT_TEST = (".venv/bin/python", "-m", "pytest", "tests", "-q", "--junitxml=test-results/unit.xml")
ACCEPTANCE_TEST = (
    ".venv/bin/python", "-m", "pytest", "acceptance", "-q", "--junitxml=test-results/acceptance.xml",
)

UNIT_GUIDE = """Unit tests go in `tests/`, named `test_<module>.py`, as plain pytest functions
that import the product's modules directly (`from {{package}}.<module> import ...`).
Install a new dependency by adding it to `requirements.txt` (or
`requirements-dev.txt` for test-only tools) and running
`.venv/bin/python -m pip install -r requirements.txt`. Run the unit tests with
`.venv/bin/python -m pytest tests`. Never start a server yourself."""

#: How an acceptance test names the criterion it proves. Python test names are
#: identifiers, so the id is written into the function name.
NAMING = """Name each test after the criterion it proves: `test_ac3_<what_it_checks>` for
AC-3 (a test that proves two writes both: `test_ac3_ac4_<...>`). A test with no
criterion id in its name proves nothing the harness can count."""


#: A pytest failure raised by the test's own code: a name it never defined, a
#: fixture that does not exist, a file that does not parse. An ImportError or
#: AttributeError is left out: before anything is built, the product's module
#: or function not existing yet is exactly what a test should fail on.
TEST_BUGS = (
    r"\bNameError\b",
    r"\b(?:SyntaxError|IndentationError)\b",
    r"fixture '[^']+' not found",
)
