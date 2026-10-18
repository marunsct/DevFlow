"""A command that hits its time limit returns what it printed, and the Python packs say to close what tests open (plan item AV).

The hang itself was ended by the earlier fixes (`2f68304`, `4abd460`); two things
stayed open. A timeout returned an error and nothing of the output, so a stage
could not tell a hang after the results from a hang before them; and the Python
guides never said that an async database engine opened at import keeps pytest alive.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from app.stacks.packs import ALL_PACKS, _fullstack, _python
from app.tools import sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_timeout_carries_the_output_printed_before_the_limit(tmp_path):
    script = tmp_path / "slow.py"
    script.write_text("import time\nprint('3 tests ran', flush=True)\nprint('about to hang', flush=True)\ntime.sleep(60)\n")

    with pytest.raises(subprocess.TimeoutExpired) as raised:
        sandbox._run_and_watch_the_tree([sys.executable, str(script)], cwd=str(tmp_path), env={"PATH": "/usr/bin:/bin"}, timeout=3)

    assert "3 tests ran" in raised.value.output and "about to hang" in raised.value.output


def test_the_timeout_answer_says_it_was_ended_at_the_limit_and_shows_the_tail():
    import inspect

    source = inspect.getsource(sandbox)
    assert "it was ended at the time limit. Its output so far is in stdout and stderr." in source
    assert "expired.stdout" in source


def test_the_python_guides_say_to_close_what_tests_open():
    for text in (_python.UNIT_GUIDE, _fullstack.FASTAPI.guide):
        flat = " ".join(text.split())
        assert "engine.dispose()" in flat and "never at import time" in flat
        assert not BANNED.search(text)
    assert any("engine.dispose()" in pack.guide for pack in ALL_PACKS if pack.language == "python" or "fastapi" in pack.name)
