"""No `conftest.py` above the acceptance suite is loaded when a Python pack runs it, so the product cannot skip it.

Measured on one run: a root `conftest.py` written for a work order skipped a locked acceptance test in
`pytest_collection_modifyitems`; the suite's own writer, who may write only `acceptance/`, could not take it out.
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET

from app.stacks.packs import _python


def _project(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\naddopts = -p no:cacheprovider\n")
    (tmp_path / "conftest.py").write_text(
        "import pytest\n\n"
        "def pytest_collection_modifyitems(config, items):\n"
        "    for item in items:\n"
        "        item.add_marker(pytest.mark.skip(reason='kept quiet'))\n")
    (tmp_path / "product.py").write_text("def answer():\n    return 41\n")
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "conftest.py").write_text("import pytest\n\n@pytest.fixture\ndef expected():\n    return 42\n")
    (tmp_path / "acceptance" / "test_ac1.py").write_text(
        "from product import answer\n\ndef test_ac1_answer(expected):\n    assert answer() == expected\n")
    return tmp_path


def _outcome(tmp_path, argv):
    subprocess.run([sys.executable, *argv[1:]], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    case = ET.parse(tmp_path / "test-results" / "acceptance.xml").getroot().find(".//testcase")
    return "skipped" if case.find("skipped") is not None else "failed" if case.find("failure") is not None else "passed"


def test_the_locked_test_runs_and_its_own_conftest_still_loads(tmp_path):
    project = _project(tmp_path)
    assert _outcome(project, _python.ACCEPTANCE_TEST) == "failed", "the product's skip hook was not loaded"


def test_without_the_cut_the_product_skipped_it(tmp_path):
    project = _project(tmp_path)
    old = tuple(a for a in _python.ACCEPTANCE_TEST if not a.startswith("--confcutdir"))
    assert _outcome(project, old) == "skipped"
