"""The drafting builder is given the pack's guide, the installed packages' real exports and the compiler's errors.

Measured over a night of small-model runs on a TypeScript service: `./app.js` for `./app.ts`, a router handed to
`app.use`, `json` imported from `hono` and the path `hono/middleware` each cost a run its first half hour; each is stated
in the pack's guide or readable in the installed package, and the drafting stage saw neither - the fixers did, a round
later. Behind `BUILDER_FACTS`.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.graph import builder_facts, drafting
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDER_FACTS", "on")
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    project = tmp_path / "notes"
    hono = project / "node_modules" / "hono"
    (hono / "dist").mkdir(parents=True)
    (project / "package.json").write_text(json.dumps({
        "dependencies": {"hono": "^4.6.0"}, "devDependencies": {"typescript": "^5", "@types/node": "^22"}}))
    (hono / "package.json").write_text(json.dumps({"name": "hono", "exports": {
        ".": {"types": "./dist/index.d.ts"}, "./cors": "./dist/cors.js", "./body-limit": "./dist/body-limit.js"}}))
    (hono / "dist" / "index.d.ts").write_text("export declare class Hono {}\nexport type { Context } from './context';\n")
    return tmp_path


def test_the_section_holds_the_guide_and_what_the_package_exports(workspace):
    text = builder_facts.section(workspace, "notes/src/app.ts")

    assert "app.route" in text and "./x.ts" in text          # the pack's guide
    assert "`hono` exports: Context, Hono" in text
    assert "`hono/body-limit`" in text and "`hono/cors`" in text
    assert "typescript" not in text                           # tooling is left out
    assert not BANNED.search(text.split("--- What the installed")[-1])


def test_off_the_request_is_as_it_was(workspace, monkeypatch):
    monkeypatch.setenv("BUILDER_FACTS", "off")
    assert builder_facts.section(workspace, "notes/src/app.ts") == ""
    assert builder_facts.compiler_lines(workspace, ["notes/src/app.ts"], lambda *a: {"stdout": "x"}) == []


def test_the_draft_request_carries_it(workspace):
    task = SimpleNamespace(files=["notes/src/app.ts"], interfaces=[], task_description="Build the app",
                           acceptance_criteria=[])
    request = drafting.draft_request(workspace, "notes/src/app.ts", task, None, None)

    assert "What the installed packages really export" in request
    assert "How this stack is used in this project" in request


def test_the_redraft_is_told_what_the_compiler_says_about_its_file(workspace):
    def runner(argv, category, working_directory):
        assert argv == ["npm", "run", "typecheck"] and working_directory == "notes"
        return {"stdout": "src/app.ts(25,21): error TS2769: No overload matches this call.\n"
                          "src/other.ts(1,1): error TS2304: Cannot find name 'x'.\n"}

    lines = builder_facts.compiler_lines(workspace, ["notes/src/app.ts"], runner)

    assert lines == ["- In `notes/src/app.ts` line 25: No overload matches this call."]


def test_a_python_project_is_told_what_its_installed_modules_define(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDER_FACTS", "on")
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    contract.write(tmp_path, pack_named("python-http-api"), "tasks", "Tasks")
    project = tmp_path / "tasks"
    site = project / ".venv" / "lib" / "python3.12" / "site-packages" / "jwt"
    site.mkdir(parents=True)
    (site / "__init__.py").write_text("def encode(p, k):\n    pass\n\ndef decode(t, k):\n    pass\n")
    (project / "requirements.txt").write_text("jwt==1.3.1\nfastapi>=0.110\n")

    text = builder_facts.section(tmp_path, "tasks/tasks_api/auth.py")

    assert "`jwt` defines: decode, encode" in text


def test_a_list_cut_short_says_how_many_more_there_are(workspace, monkeypatch):
    monkeypatch.setattr(builder_facts, "MOST_PATHS", 1)
    text = builder_facts.section(workspace, "notes/src/app.ts")
    assert "`hono/body-limit` and 1 more" in text
