"""A test that never ends fails alone instead of hanging the whole suite (Python packs).

One run's acceptance suite had a test run `subprocess.run(["bash", "start.sh"])`:
the script starts the service and never returns, so the suite hung to the
command's 300-second limit and no test reported anything. pytest has no time
limit per test of its own; JavaScript's runners do. Every pack that writes a
`pytest.ini` now sets one and installs the plugin that enforces it.
"""
from __future__ import annotations

from app.stacks.packs import ALL_PACKS


def _rendered(pack):
    return pack.render("notes-api", "Notes API", None)


def test_every_pack_that_writes_a_pytest_ini_limits_each_test_and_installs_what_enforces_it():
    seen = 0
    for pack in ALL_PACKS:
        files = _rendered(pack)
        ini = next((text for name, text in files.items() if name.endswith("pytest.ini")), None)
        if ini is None:
            continue
        seen += 1
        assert "\ntimeout = " in ini, pack.name
        requirements = "\n".join(text for name, text in files.items() if name.endswith("requirements-dev.txt"))
        assert "pytest-timeout" in requirements, pack.name
    assert seen >= 5


def test_the_limit_is_well_inside_the_command_s_own():
    import re

    from app.stacks.packs import _python

    seconds = int(re.search(r"timeout = (\d+)", _python.PYTEST_INI).group(1))
    assert 30 < seconds < 300
