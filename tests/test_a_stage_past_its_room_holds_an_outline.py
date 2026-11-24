"""A reading stage past its memory's room holds an outline of every code file it does not hold whole (LF.1287).

Measured on one medium run: the product numbered was about four times the memory a reading stage is given, so 32-37
of its 45 files were "Not included here" and its map of them had no line numbers, at most twelve definitions a file,
and a test file's two or three helper functions in place of its tests. A stage that needed one function read the
whole file into its conversation; a summary deleted it and it read it again. An outline with each definition's and
each test's lines lets it read the lines it needs. A product whose files fit is sent exactly as before.
"""
from __future__ import annotations

import re

from app.agents import project_memory
from app.agents.review_files import held_section

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _settings(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "65536")
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("CANONICAL_MEMORY", "on")


def _a_module(n: int) -> str:
    """About 8,000 characters: settings, then a handler defined at line 150, then its body."""
    lines = [f"SETTING_{k} = 'module {n} keeps {k}'" for k in range(149)]
    lines += [f"def handler_{n}(request):", *[f"    step_{k} = {k}" for k in range(120)], "    return step_0"]
    return "\n".join(lines) + "\n"


def _a_large_product(root, count: int = 30) -> list[str]:
    names = []
    for n in range(count):
        name = f"app/m{n:02}.py"
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(_a_module(n))
        names.append(name)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "technical_specification.md").write_text(
        "# Specification\n" + "".join(f"## Section {k}\n" + "The product keeps its records.\n" * 30 for k in range(40)))
    return names


def _memory(root, names) -> tuple[str, dict[str, str]]:
    return project_memory.render_for_a_review(root, None, "", "security_review", names)


def test_every_code_file_is_whole_or_outlined_with_its_lines(tmp_path, monkeypatch):
    _settings(monkeypatch)
    names = _a_large_product(tmp_path)

    memory, held = _memory(tmp_path, names)

    assert "app/m29.py" not in held, "the arrangement: the last file does not fit"
    assert re.search(r"^  150-271  def handler_29\(request\)$", memory, re.M)
    for name in names:
        assert name in held or f"\n{name} (271 lines)\n" in memory


def test_a_test_file_s_outline_names_its_tests(tmp_path, monkeypatch):
    _settings(monkeypatch)
    names = _a_large_product(tmp_path)
    suite = "acceptance/records.spec.js"
    (tmp_path / "acceptance").mkdir()
    body = ["import { test, expect } from '@playwright/test';", "function signUp(page) { return page; }",
            "function signIn(page) { return page; }"]
    for n in range(10):
        body += [f"test('[AC-{n}] keeps record {n}', async ({{ page }}) => {{",
                 *[f"  await expect(page.getByText('record {n} part {k}')).toBeVisible();" for k in range(16)], "});"]
    (tmp_path / suite).write_text("\n".join(body) + "\n")

    memory, held = _memory(tmp_path, [*names, suite])

    assert suite not in held
    for n in range(10):
        first = 4 + 18 * n
        assert f"  {first}-{first + 17}  test: [AC-{n}] keeps record {n}\n" in memory


def test_an_outline_entry_ends_where_the_next_begins():
    from app.analysis import outline

    text = ("class Store:\n"
            "    def add(self, item):\n"
            "        self.items.append(item)\n"
            "\n"
            "    def remove(self, item):\n"
            "        self.items.remove(item)\n"
            "\n"
            "\n"
            "def make_store():\n"
            "    return Store()\n")

    assert outline.entries("store.py", text) == [
        (1, 6, "class Store"), (2, 3, "def add(self, item)"), (5, 6, "def remove(self, item)"),
        (9, 10, "def make_store()"),
    ]


def test_a_marker_line_is_shown_with_its_definition():
    from app.analysis import outline

    text = ('router = Router()\n'
            '\n'
            '@router.get("/records/{id}")\n'
            'async def one_record(id: int):\n'
            '    return find(id)\n'
            '\n'
            '# The records a person may see.\n'
            'def visible_records(person):\n'
            '    return []\n')

    assert outline.entries("routes.py", text) == [
        (3, 5, '@router.get("/records/{id}")  async def one_record(id: int)'),
        (7, 9, "def visible_records(person)"),
    ]


def test_a_closing_brace_marks_nothing():
    from app.analysis import outline

    text = "class Store {\n  add(item) { return item; }\n}\nfunction makeStore() {\n  return new Store();\n}\n"

    assert outline.entries("store.js", text) == [(1, 3, "class Store"), (4, 6, "function makeStore()")]


def test_an_outline_reads_a_language_with_no_import_reader(tmp_path, monkeypatch):
    _settings(monkeypatch)
    names = _a_large_product(tmp_path)
    kotlin = "src/main/kotlin/Greeter.kt"
    (tmp_path / kotlin).parent.mkdir(parents=True)
    (tmp_path / kotlin).write_text("package app\n\n"
                                   "data class User(val name: String)\n\n"
                                   "object Greeter {\n"
                                   "    fun greet(user: User): String {\n"
                                   "        return \"Hello, \" + user.name\n"
                                   "    }\n"
                                   "}\n" + "// what the greeter is for\n" * 400)

    memory, held = _memory(tmp_path, [*names, kotlin])

    assert kotlin not in held
    assert "  3-3  data class User(val name: String)\n" in memory
    assert "  6-8  fun greet(user: User): String\n" in memory


def test_the_outline_sentence_uses_no_banned_word(tmp_path, monkeypatch):
    _settings(monkeypatch)
    names = _a_large_product(tmp_path)
    memory, _ = _memory(tmp_path, names)
    heading = next(line for line in memory.splitlines() if line.startswith("=== Outline"))
    told = [held_section(["app/m00.py"]), held_section(["app/m00.py"], "technical_lead")]

    assert all("read only the lines you need, by range" in text for text in told), "the request says how to read"
    assert not any(BANNED.search(text) for text in [heading, *told])


def test_a_product_that_fits_has_no_outline(tmp_path, monkeypatch):
    """Guard: a review whose files fit is rendered as before - no outline, the map of files left out as it was."""
    _settings(monkeypatch)
    names = [f"app/r{n}.py" for n in range(3)]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("def route():\n    return 1\n")

    memory, held = project_memory.render_for_a_stage(tmp_path, None, "Review the routes.", "security_review")

    assert set(names) <= set(held)
    assert "=== Outline" not in memory and "(numbered lines" not in memory
