"""Every file a stage writes is parsed in its own language, at the write.

Python, JSON and JavaScript were. One run's `playwright.config.ts` was written
one comma short, accepted - nothing in the worker parsed TypeScript - and every
browser test then failed to start. Three test rounds described that three
different ways, and the sprint ran out of attempts three hours later with no
stage having been told what a parser reports in a millisecond.

Which languages a write may be *refused* on was measured, not assumed: each
grammar was run over real projects and is listed only if it reported nothing in
any file its compiler accepts. The rest keep the bracket count, which warns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis import grammar_parse, typescript_parse
from app.analysis.grammar_parse import is_certain, parse_problem
from app.analysis.syntax_balance import structural_problem
from app.tools import repository
from app.tools.repository import RepositoryToolError, write_approved_artifact

pytest.importorskip("tree_sitter_language_pack")

ONE_COMMA_SHORT = (
    "import { defineConfig } from '@playwright/test';\n\n"
    "export default defineConfig({\n  testDir: 'tests'\n  webServer: { command: 'x' }\n});\n"
)

BROKEN = {
    "Main.java": "class Main { void f() { int x = ; } }\n",
    "main.go": 'package main\nfunc main() { println("x" }\n',
    "lib.rs": "fn main() { let x = 1 }}\n",
    "a.rb": "def f\n  puts 1\n",
    "a.php": "<?php\nfunction f() { return 1 \n}\n",
    "a.lua": "local function f() return 1\n",
    "c.yaml": "a:\n  - b\n c: 1\n",
    "c.toml": "a = [1, 2\n",
    "c.xml": "<a><b></a>\n",
    "index.html": "<html><body><script>\nfunction f() { if (x { }\n</script></body></html>\n",
}

SOUND = {
    "Main.java": "class Main { void f() { int x = 1; } }\n",
    "main.go": 'package main\nfunc main() { println("x") }\n',
    "lib.rs": "fn main() { let x = 1; }\n",
    "a.rb": "def f\n  puts 1\nend\n",
    "a.php": "<?php\nfunction f() { return 1; }\n",
    "a.lua": "local function f() return 1 end\n",
    "c.yaml": "a:\n  - b\nc: 1\n",
    "c.toml": "a = [1, 2]\n",
    "c.xml": "<a><b></b></a>\n",
    "index.html": "<html><body><script type=\"module\">\nimport {a} from './a.js';\nawait a();\n</script></body></html>\n",
}


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_a_broken_file_is_named_with_its_line(name: str) -> None:
    problem = parse_problem(name, BROKEN[name])

    assert problem, name
    assert is_certain(name)
    assert structural_problem(name, BROKEN[name]) == problem


@pytest.mark.parametrize("name", sorted(SOUND))
def test_a_sound_file_is_left_alone(name: str) -> None:
    assert parse_problem(name, SOUND[name]) is None


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_the_write_is_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(tmp_path, f"proj/{name}", BROKEN[name])

    assert not (tmp_path / "proj" / name).exists()
    assert "Nothing was written" in str(refused.value)


@pytest.mark.parametrize("name, content", [
    # Not YAML until a template engine has filled it in.
    ("chart/templates/deploy.yaml", "replicas: {{ .Values.replicas }}\n{{- if .Values.on }}\na: 1\n{{- end }}\n"),
    # A block that is data, and one a browser fetches from elsewhere.
    ("page.html", '<script type="application/json">{not js</script><script src="a.js"></script>'),
    # Entities come from a DTD nothing here fetches.
    ("doc.xml", "<a>&nbsp;</a>\n"),
    # Languages whose grammar measured wrong about correct files are not judged by it.
    ("a.kt", "fun main() { println(\"x\") }\n"),
    ("a.swift", "struct A { let x: Int }\n"),
    ("a.cs", "#if DEBUG\nclass A { }\n#endif\n"),
])
def test_what_a_parser_cannot_judge_is_not_judged(name: str, content: str) -> None:
    assert parse_problem(name, content) is None


def test_a_language_without_an_exact_parser_keeps_the_bracket_count(tmp_path: Path) -> None:
    result = write_approved_artifact(tmp_path, "proj/a.kt", 'fun main() { println("x")\n')

    assert (tmp_path / "proj" / "a.kt").exists()
    assert "do not balance" in str(result)


def test_the_script_inside_a_page_is_reported_at_the_page_s_own_line() -> None:
    page = "<html>\n<body>\n<p>hi</p>\n<script>\nconst a = 1;\nfunction f() { if (x { }\n</script>\n</body></html>\n"

    problem = parse_problem("index.html", page)

    assert problem and "line 6" in problem
    assert ">    6 | function f() { if (x { }" in problem


def test_a_grammar_s_refusal_gives_way_to_the_same_file_sent_a_third_time(tmp_path: Path) -> None:
    """A grammar is a measurement, not the compiler. If it is ever wrong about
    a file, a stage must not be locked out of writing it."""
    repository._REFUSED_ON_A_GRAMMAR.clear()
    for _ in range(repository.GRAMMAR_REFUSALS_BEFORE_IT_IS_WRITTEN):
        with pytest.raises(RepositoryToolError):
            write_approved_artifact(tmp_path, "proj/Main.java", BROKEN["Main.java"])

    result = write_approved_artifact(tmp_path, "proj/Main.java", BROKEN["Main.java"])

    assert (tmp_path / "proj" / "Main.java").exists()
    assert "does not parse as Java" in str(result)


def test_the_parser_that_loads_the_file_is_never_overruled(tmp_path: Path) -> None:
    repository._REFUSED_ON_A_GRAMMAR.clear()
    for _ in range(5):
        with pytest.raises(RepositoryToolError):
            write_approved_artifact(tmp_path, "proj/c.toml", BROKEN["c.toml"])
    assert not (tmp_path / "proj" / "c.toml").exists()


def test_the_check_says_nothing_when_the_grammars_are_not_installed(monkeypatch) -> None:
    monkeypatch.setattr(grammar_parse, "_parser", lambda language: None)

    assert parse_problem("Main.java", BROKEN["Main.java"]) is None
    assert not is_certain("Main.java")


# --- TypeScript: the compiler's own parser, wherever one can be found ---------

needs_the_compiler = pytest.mark.skipif(
    typescript_parse.compiler_for(None) is None,
    reason="no TypeScript compiler is installed beside Node on this machine",
)


@needs_the_compiler
def test_typescript_one_comma_short_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(tmp_path, "proj/playwright.config.ts", ONE_COMMA_SHORT)

    assert "',' expected" in str(refused.value)
    assert not (tmp_path / "proj" / "playwright.config.ts").exists()


@needs_the_compiler
@pytest.mark.parametrize("name, content", [
    ("a.ts", "export const x: number = 1;\nenum E { A }\nexport default x satisfies unknown;\n"),
    ("a.tsx", "const A = () => <div>{[1].map(i => <b key={i}>{i}</b>)}</div>;\nexport default A;\n"),
    ("a.jsx", "export const A = () => <div><span /></div>;\n"),
])
def test_sound_typescript_and_jsx_are_written(tmp_path: Path, name: str, content: str) -> None:
    write_approved_artifact(tmp_path, f"proj/{name}", content)

    assert (tmp_path / "proj" / name).read_text(encoding="utf-8") == content


def test_without_a_compiler_the_grammar_s_reading_is_a_note(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(typescript_parse, "compiler_for", lambda path: None)

    result = write_approved_artifact(tmp_path, "proj/playwright.config.ts", ONE_COMMA_SHORT)

    assert (tmp_path / "proj" / "playwright.config.ts").exists()
    assert "may not parse as TypeScript" in str(result)


def test_a_project_s_own_compiler_is_the_one_asked(tmp_path: Path) -> None:
    own = tmp_path / "proj" / "node_modules" / "typescript" / "lib"
    own.mkdir(parents=True)
    (own / "typescript.js").write_text("", encoding="utf-8")

    found = typescript_parse.compiler_for(tmp_path / "proj" / "src" / "a.ts")

    assert found == str(tmp_path / "proj" / "node_modules" / "typescript")
