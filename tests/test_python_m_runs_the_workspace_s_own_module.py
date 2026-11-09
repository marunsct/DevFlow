"""`python -m` may run the product's own package, as it may run the product's own files; nothing else new.

Measured on one release: every contract line of a command-line tool was `python -m <its package> ...`, and each was
refused as "arbitrary code", so none was checked.
"""
from __future__ import annotations

import pytest

from app.tools.sandbox import CommandNotAllowed, validate_command


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "word-tool" / "wordstats").mkdir(parents=True)
    (tmp_path / "word-tool" / "wordstats" / "__init__.py").write_text("")
    (tmp_path / "word-tool" / "wordstats" / "__main__.py").write_text("print('ok')\n")
    (tmp_path / "word-tool" / "single.py").write_text("print('ok')\n")
    (tmp_path / "word-tool" / ".venv" / "lib" / "evil").mkdir(parents=True)
    (tmp_path / ".venv" / "hidden").mkdir(parents=True)
    (tmp_path / ".venv" / "hidden" / "__init__.py").write_text("")
    return tmp_path


@pytest.mark.parametrize("module", ["wordstats", "wordstats.cli", "single"])
def test_the_product_s_own_module_runs(workspace, module):
    assert validate_command(["python3", "-m", module, "sample.txt"], "testing_specialist", workspace)[2] == module


@pytest.mark.parametrize("module", ["http.server", "hidden", "evil", "os"])
def test_any_other_module_is_still_refused(workspace, module):
    with pytest.raises(CommandNotAllowed, match="arbitrary code"):
        validate_command(["python3", "-m", module], "testing_specialist", workspace)


def test_the_tools_stay_allowed(workspace):
    assert validate_command(["python3", "-m", "pytest", "-q"], "testing_specialist", workspace)
