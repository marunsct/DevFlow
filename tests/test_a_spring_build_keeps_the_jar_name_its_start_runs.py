"""The Spring service's build is held to the jar name its start script and Dockerfile run, at every round.

Measured on one Java run: a work order rewrote `pom.xml` without `<finalName>app</finalName>`; the build made
`notes-api-1.0.0.jar`, and every start of the product said "Unable to access jarfile target/app.jar" for a whole
attempt while the fixers worked on the routes.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.graph import acceptance_nodes
from app.stacks import contract, entry_exports, pack_named


def _a_spring_project(tmp_path, monkeypatch, pom):
    monkeypatch.setenv("PACK_ENTRY_EXPORTS_KEPT", "on")
    pack = pack_named("java-spring-api")
    contract.write(tmp_path, pack, "notes-api", "Notes", None, scaffolded=True)
    for relative, text in pack.render("notes-api", "Notes", None).items():
        (tmp_path / "notes-api" / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes-api" / relative).write_text(text)
    if pom is not None:
        (tmp_path / "notes-api" / "pom.xml").write_text(pom(pack.render("notes-api", "Notes", None)["pom.xml"]))
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


@pytest.mark.parametrize("pom, raised", [
    (None, False),
    (lambda text: re.sub(r"\s*<finalName>app</finalName>", "", text), True),
], ids=["the-scaffold", "jar-name-dropped"])
def test_a_build_without_the_jar_name_is_raised_against_its_pom(tmp_path, monkeypatch, pom, raised):
    state = _a_spring_project(tmp_path, monkeypatch, pom)

    found = [d for d in acceptance_nodes.pack_contract_defects(state) if entry_exports.NO_LONGER_DECLARES in d.description]

    assert bool(found) is raised
    if raised:
        assert found[0].affected_files == ["notes-api/pom.xml"]
        assert "<finalName>app</finalName>" in found[0].description
