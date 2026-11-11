"""The stages that write and judge the specification are told the files the setup writes and the dependencies it declares.

Measured on one run: the design review blocked on "missing wsgi.py" and "gunicorn not declared"; the setup had
written `wsgi.py` and a requirements file declaring gunicorn, but the review was told only of the kept files, and the
specification went back twice and escalated.
"""
from __future__ import annotations

import re

from app.agents.shared_facts import what_the_setup_decides
from app.stacks import pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_a_python_service_s_starter_files_and_dependencies_are_named():
    said = "\n".join(what_the_setup_decides(pack_named("python-flask-api"), "notes-api", "notes_api"))
    assert "`notes-api/notes_api/wsgi.py`" in said and "`notes-api/requirements.txt`" in said
    assert "`gunicorn>=23`" in said and "`flask>=3.1`" in said
    assert "pytest" not in said.split("runtime dependencies")[1]  # the development manifest is not runtime
    assert "`notes-api/start.sh`" not in said.split("The setup writes")[1].split(": none")[0]  # kept: said elsewhere


def test_a_node_service_s_manifest_dependencies_are_named():
    said = "\n".join(what_the_setup_decides(pack_named("node-hono-native-api"), "notes-api", None))
    assert "`hono`" in said and "`notes-api/package.json`" in said


def test_the_words_name_no_product():
    said = "\n".join(what_the_setup_decides(pack_named("browser-react"), "app", None))
    assert not BANNED.search(said.split("The setup writes")[1])


def test_the_starter_files_are_not_said_to_exist_before_the_build():
    """Measured on two runs: told the setup "has already written" its starter files, the architect read them before
    the setup had run and was told no such file exists yet. The line holds at every stage."""
    said = "\n".join(what_the_setup_decides(pack_named("python-flask-api"), "notes-api", "notes_api"))
    line = next(x for x in said.splitlines() if "`notes-api/requirements.txt`" in x)
    assert "already" not in line
    assert "when the build starts" in line and "not on disk" in line
    assert not BANNED.search(line)
