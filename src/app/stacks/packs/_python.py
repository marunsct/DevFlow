"""What every Python pack shares: a virtual environment and pytest with JUnit reports."""

from __future__ import annotations

import ast
from collections.abc import Callable, Sequence

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
#: `--confcutdir=acceptance`: no `conftest.py` above the suite is loaded. Measured on one run: a root `conftest.py` a
#: builder wrote skipped a locked acceptance test in `pytest_collection_modifyitems`, and the suite's writer, who may
#: write only `acceptance/`, could not take it out. The kept `pytest.ini` puts the project on the import path itself.
ACCEPTANCE_TEST = (
    ".venv/bin/python", "-m", "pytest", "acceptance", "-q", "--confcutdir=acceptance",
    "--junitxml=test-results/acceptance.xml",
)


def pytest_selection(argv: Sequence[str], due: Sequence[str], files: Sequence[str]) -> tuple[str, ...] | None:
    """The suite's command asking pytest for the tests named after `due`, its files in the order given; or None.

    pytest runs the files it is given in that order, so they replace the suite's folder. A test name carries its id
    as `test_ac3_...` (or `test_ac_3_...`); `-k` matches part of a name, ignoring case.
    """
    from app.acceptance.junit import TAG  # noqa: PLC0415 - the id grammar is the suite's

    argv = list(argv)
    if "-k" in argv or not (due or files):
        return None
    if files:
        if "acceptance" not in argv:
            return None
        at = argv.index("acceptance")
        argv[at:at + 1] = list(files)
    if due:
        words: list[str] = []
        for item in due:
            found = TAG.fullmatch(str(item).strip())
            if found:
                kind, number = found.group(1).lower(), int(found.group(2))
                words += [f"{kind}{number}_", f"{kind}_{number}_"]
        if not words:
            return None
        argv += ["-k", " or ".join(dict.fromkeys(words))]
    return tuple(argv)

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

#: Measured on one run: tests imported a helper from `conftest` in a folder with `__init__.py`; the second copy of the
#: module had empty state, and no test of 46 reached the product.
SHARED_HELPERS = """

Share a helper through a fixture in `conftest.py`, or from a module of its own: a test
never imports `conftest` by name, because pytest has loaded that file under another
name and the import makes a second copy with empty state."""


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
#: Measured on one FastAPI run (14 repeats over three rounds): unit tests wrapped their setup in
#: `patch.object(app.state, 'db_path', ...)` while the product never defines that attribute, so every test failed in its
#: fixture with `<State object> does not have the attribute 'db_path'`; the fixers rewrote the product's startup, not the tests.
PYTHON_KNOWN_ERRORS["does not have the attribute"] = (
    "`mock.patch.object(target, 'name', value)` needs `name` to exist on `target` already: the test names an attribute "
    "the product never defines. Read what the product really reads (a module-level setting, an environment variable "
    "such as `DATA_DIR`, a dependency it takes) and patch or set that in every test of the file in one rewrite, or "
    "pass `create=True` for a name only the test adds. Do not add the attribute to the product only to satisfy one test."
)
#: Measured on one Flask run: the product did not start and the unit tests failed with this message 92 times over three
#: rounds; each fix rewrote the entry file or the tests and none named the rule.
PYTHON_KNOWN_ERRORS["working outside of application context"] = (
    "Flask's `current_app`, `g` and `request` exist only while an application or request context is active. Code that "
    "uses them at import time, at start-up before the app is served, or in a unit test that calls the function "
    "directly fails with this. Do the start-up work inside `with app.app_context():`, or give the function the app or "
    "the connection as a parameter instead of reading `current_app`; in a test, call it inside "
    "`with app.app_context():` (a fixture) or through `app.test_client()`."
)
#: Measured on one run: `DELETE /items/99999999999999999999` answered 500 on a Flask service on SQLite - its `<int:...>`
#: path converter takes an integer of any size, and sqlite3 refused it before the query ran; five fixes in a row did not
#: find it.
PYTHON_KNOWN_ERRORS["python int too large to convert to sqlite integer"] = (
    "an id or number from the request is larger than SQLite's 64-bit INTEGER, and sqlite3 refuses it before the query "
    "runs: check that a number taken from the path or the body fits between -9223372036854775808 and "
    "9223372036854775807 before it reaches the database, and answer the status the specification gives for a record "
    "that does not exist (usually 404) or for an invalid value."
)

#: Measured on one run: every fix of a full-stack product was reverted because the service no longer started -
#: `(sqlite3.OperationalError) index ix_... already exists` on `CREATE INDEX` - for three rounds.
PYTHON_KNOWN_ERRORS["operationalerror) index "] = (
    "the same index is created twice: a column declared with `index=True` and an `Index(...)` of the same name in "
    "`__table_args__` (or two models naming one index), or an index created by hand on a database file an earlier start "
    "already made. Declare each index once - `index=True` or an `Index(...)`, not both - and create the tables with "
    "`Base.metadata.create_all(engine)`, which skips what already exists."
)


#: The methods of a request a suite makes through a client: `client.post(...)`, `requests.get(...)`, `session.put(...)`.
_REQUEST_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "request", "urlopen"})
#: The most a loop is taken to repeat: a bound past it is a stress test, not a count to multiply.
_MOST_LOOP_REPEATS = 1_000


def client_calls(texts: Sequence[str], names_the_route: Callable[[str], bool] | None) -> tuple[list[int], int]:
    """(how many requests to one route each test that runs makes, how many once-a-session fixtures make).

    The Python reader of `_javascript.client_calls`: `names_the_route` says whether a string's text is an address of
    that route (None counts every request call). A request is counted where the code names the route - a string, an
    f-string's text, or a module constant holding one - in a `test_` function or method, in a function it calls at any
    depth, in a fixture it names among its parameters (a fixture of wider scope than a function once a run), and inside
    `for _ in range(n)` with a literal `n` as often as the loop runs. Never raises; ([], 0) on any doubt.
    """
    try:
        trees = [ast.parse(text) for text in texts]
        functions: dict[str, list[ast.AST]] = {}
        widely_scoped: set[str] = set()
        constants: set[str] = set()
        for tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.setdefault(node.name, []).append(node)
                    for decorator in node.decorator_list:
                        scope = next((k.value for k in getattr(decorator, "keywords", [])
                                      if k.arg == "scope" and isinstance(k.value, ast.Constant)), None)
                        if scope is not None and scope.value != "function":
                            widely_scoped.add(node.name)
            if names_the_route is not None:
                for node in tree.body:
                    if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str) and names_the_route(node.value.value)):
                        constants.update(t.id for t in node.targets if isinstance(t, ast.Name))
        cost: dict[str, int] = {}

        def text_of(node: ast.AST) -> str | None:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.JoinedStr):
                return "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in node.values)
            return None

        def direct(node: ast.AST) -> int:
            if names_the_route is None:
                return int(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                           and node.func.attr in _REQUEST_METHODS)
            said = text_of(node)
            if said is not None:
                return int(names_the_route(said))
            return int(isinstance(node, ast.Name) and node.id in constants and isinstance(node.ctx, ast.Load))

        def calls(node: ast.AST, open_: frozenset[str]) -> int:
            if isinstance(node, ast.Expr) and text_of(node.value) is not None:
                return 0  # a docstring says, it does not ask
            total = direct(node)
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else "")
                if called in functions and called not in open_:
                    total += of(called, open_)
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(node, ast.JoinedStr):
                    continue
                total += calls(child, open_)
            if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.iter, ast.Call) \
                    and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range" \
                    and all(isinstance(a, ast.Constant) and isinstance(a.value, int) for a in node.iter.args) \
                    and 1 <= len(node.iter.args) <= 2:
                bounds = [a.value for a in node.iter.args]
                repeats = bounds[-1] - (bounds[0] if len(bounds) == 2 else 0)
                if 1 < repeats <= _MOST_LOOP_REPEATS:
                    total += (repeats - 1) * sum(calls(child, open_) for child in node.body)
            return total

        def body_cost(function: ast.AST, open_: frozenset[str]) -> int:
            return sum(calls(statement, open_) for statement in function.body)

        def of(name: str, open_: frozenset[str]) -> int:
            if name not in cost:
                cost[name] = max(body_cost(function, open_ | {name}) for function in functions[name])
            return cost[name]

        per_test: list[int] = []
        once = sum(of(name, frozenset()) for name in widely_scoped)
        for tree in trees:
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test"):
                    continue
                if any("skip" in ast.unparse(decorator) for decorator in node.decorator_list):
                    continue
                named = [a.arg for a in node.args.args if a.arg in functions and a.arg not in widely_scoped]
                per_test.append(body_cost(node, frozenset({node.name})) + sum(of(n, frozenset()) for n in named))
        return per_test, once
    except Exception:  # noqa: BLE001 - nothing counted is nothing found
        return [], 0
