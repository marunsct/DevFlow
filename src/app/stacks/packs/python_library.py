"""A library in Python: a package other programs import."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _python

PYPROJECT = """[project]
name = "{{project}}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
"""

INIT = '''"""{{title}}.

Everything a caller may use is imported here and listed in `__all__`.
"""

__version__ = "0.1.0"

__all__: list[str] = []
'''

SMOKE_UNIT = '''import {{package}}


def test_the_package_declares_a_version():
    assert {{package}}.__version__ == "0.1.0"
'''

SMOKE_ACCEPTANCE = '''import importlib


def test_the_package_imports():
    assert importlib.import_module("{{package}}").__version__
'''

GUIDE = _python.UNIT_GUIDE + """
The package is `{{package}}/`. Its public interface is what `{{package}}/__init__.py`
imports and lists in `__all__`; everything else is internal."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `test_<feature>.py`, as pytest
functions that use the library only the way a caller would: through
`import {{package}}` and the names in its `__all__`, never internal modules. Check
return values exactly, and check that invalid input raises the error the
criteria name (`with pytest.raises(ValueError): ...`).
""" + _python.NAMING

PACK = StackPack(
    name="python-library",
    title="Library in Python",
    kind="library",
    language="python",
    frameworks=(),
    files={
        "pyproject.toml": PYPROJECT,
        "requirements.txt": "",
        "requirements-dev.txt": "pytest>=8\n",
        "pytest.ini": _python.PYTEST_INI,
        ".gitignore": _python.GITIGNORE,
        "{{package}}/__init__.py": INIT,
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
    unit_test_names=_python.UNIT_TEST_NAMES,
    test_helpers=_python.TEST_HELPERS,
    kept_files=("pytest.ini",),
    kept_scripts={},
    smoke_files={
        "tests/test_scaffold_smoke.py": SMOKE_UNIT,
        "acceptance/test_scaffold_smoke.py": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "Python",
        "framework": "None (standard library)",
        "frontend_framework": "",
        "testing_framework": "pytest for unit and acceptance tests",
    },
    check_families=frozenset({"python"}),
    test_bugs=_python.TEST_BUGS,
    ci_setup=_python.CI_SETUP,
)
