"""The single largest source of wasted tool calls, across every language.

Swept all 45 stored transcripts on 2026-09-19: of 371 costly tool failures,
247 were `edit_artifact` answering "Could not find that text" - 67%. No other
cause reached 30. Editing a file is language-independent, so this is waste the
harness pays in every stack it builds.

The repair chain already forgave line numbers, doubled backslashes, JSON
escaping, a different left margin and blank lines. Two residual faults
survived it, both measured on run-519a9d8a:

1. The repairs were applied to the original `find` one at a time and never
   composed, so a passage carrying two faults at once defeated all of them.
2. A near-miss whose only difference was indentation printed as two lines that
   look identical on screen, so the model re-sent the same text.
"""

from __future__ import annotations

import pathlib

import pytest

from app.tools.repository import (
    RepositoryToolError,
    _only_the_whitespace_differs,
    _transcription_repairs,
    edit_approved_artifact,
)


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "p").mkdir()
    return tmp_path


def test_a_find_escaped_twice_over_is_repaired(workspace):
    """`\\\\n` is a collapse away from `\\n`, which is a decode away from a newline.

    Each repair alone leaves the other fault in place, so neither candidate
    matched and the agent learned only that its text was absent.
    """
    target = workspace / "p" / "a.js"
    target.write_text('const url = "x";\nawait page.goto(url);\n', encoding="utf-8")

    result = edit_approved_artifact(
        workspace,
        "p/a.js",
        'const url = "x";\\\\nawait page.goto(url);',
        'const url = "y";\nawait page.goto(url);',
    )

    assert result.get("status") == "edited"
    assert target.read_text(encoding="utf-8").startswith('const url = "y";')


def test_line_numbers_and_escaping_together_are_repaired(workspace):
    """A passage copied out of a read carries the numbers and the escapes."""
    target = workspace / "p" / "b.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    result = edit_approved_artifact(
        workspace, "p/b.py", "1 | def add(a, b):\\n2 |     return a + b", "def add(a, b):\n    return a - b"
    )

    assert result.get("status") == "edited"


def test_the_repairs_are_composed_not_merely_listed():
    candidates = [c for c, _ in _transcription_repairs("a\\\\nb")]
    assert "a\\nb" in candidates, "the single collapse must still be offered"
    assert "a\nb" in candidates, "the composed collapse-then-decode must be offered"


def test_a_repair_never_invents_a_candidate_for_clean_text():
    assert _transcription_repairs("def add(a, b):") == []


def test_a_whitespace_only_difference_is_described_in_words(workspace):
    """Two visually identical lines teach nothing; a sentence does."""
    target = workspace / "p" / "c.js"
    target.write_text(
        "test('x', async () => {\n"
        "  const url = `file://${process.cwd()}/app/index.html`;\n"
        "  await page.goto(url);\n"
        "});\n",
        encoding="utf-8",
    )
    find = (
        "const url = `file://${process.cwd()}/app/index.html`;\n"
        "    await page.evaluate(() => addTask('T'));"
    )

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(workspace, "p/c.js", find, "x")

    message = str(caught.value)
    assert "the same text," in message, message
    assert "indented" in message, message
    # The failure this replaces: the same characters printed on both sides.
    sent = [l for l in message.splitlines() if l.strip().startswith("you sent:")]
    has = [l for l in message.splitlines() if l.strip().startswith("file has:")]
    for a, b in zip(sent, has):
        assert a.split("you sent:")[1].strip() != b.split("file has:")[1].strip().split("   (line")[0].strip(), (
            "a difference message must never print the same text on both sides"
        )


@pytest.mark.parametrize(
    "sent,actual,expect",
    [
        ("  x = 1", "    x = 1", "indented"),
        ("    x = 1", "  x = 1", "indented"),
        ("\tx = 1", "    x = 1", "spaces"),
        ("x = 1 ", "x = 1", "trailing"),
        ("x = 1", "x = 1 ", "trailing"),
        ("x = 1", "x = 2", ""),
        ("x = 1", "x = 1", ""),
    ],
)
def test_whitespace_differences_are_named_and_real_ones_are_not(sent, actual, expect):
    described = _only_the_whitespace_differs(sent, actual)
    if expect:
        assert expect in described
    else:
        assert described == "", "only a whitespace-only difference may be described as one"


def test_a_genuine_difference_still_shows_both_lines(workspace):
    """The fix must not hide a real difference behind a sentence."""
    target = workspace / "p" / "d.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(workspace, "p/d.py", "def add(a, b):\n    return a * b", "x")

    assert "return a + b" in str(caught.value)


def test_exactness_is_unchanged_by_the_repairs(workspace):
    """A repair may forgive transcription, never ambiguity."""
    target = workspace / "p" / "e.js"
    target.write_text("const a = 1;\nconst a = 1;\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(workspace, "p/e.js", "const a = 1;", "const a = 2;")

    assert "ambiguous" in str(caught.value).lower() or "twice" in str(caught.value).lower()


# ---------------------------------------------------------------------------
# The self-inflicted half: the harness quotes the file back with its own
# gutter, tells the model to copy from there, and then rejects what it copied.
# ---------------------------------------------------------------------------

from app.tools.repository import _READ_LINE_NUMBER, _without_read_line_numbers


@pytest.mark.parametrize(
    "line,expected",
    [
        ("  21  content", "content"),          # deepagents read_file
        ("   21 | content", "content"),        # this module's _closest_passage
        (">   21 | content", "content"),       # ditto, nearest-line marker
        ("21: content", "content"),            # the filesystem tool's documented shape
        ("21\tcontent", "content"),
    ],
)
def test_every_line_number_gutter_this_harness_emits_is_stripped(line, expected):
    found = _READ_LINE_NUMBER.match(line)
    assert found, f"{line!r} is a gutter this harness produces and is not recognised"
    assert line[found.end():] == expected


def test_a_passage_copied_out_of_our_own_error_message_is_repaired(workspace):
    """The loop this closes.

    `_closest_passage` prints the file with a `NN | ` gutter and a `>` marker
    and instructs "Copy the passage from there exactly". Before this, the
    stripper removed the digits and left the pipe, so the copy failed too.
    """
    target = workspace / "p" / "f.js"
    target.write_text("line one\nline two\nline three\n", encoding="utf-8")

    quoted = "     1 | line one\n>    2 | line two\n     3 | line three"
    result = edit_approved_artifact(workspace, "p/f.js", quoted, "replaced")

    assert result.get("status") == "edited"
    assert target.read_text(encoding="utf-8").strip() == "replaced"


def test_ordinary_code_is_not_mistaken_for_a_gutter():
    assert _without_read_line_numbers("x = 1") is None
    assert _without_read_line_numbers("return a + b") is None


# ---------------------------------------------------------------------------
# The structural answer: a line range has nothing to transcribe.
#
# Replaying the 75 real failures that quoted enough file to replay, the repair
# chain resolved 7 - old and new alike. Transcription repair had reached its
# limit. The redirecting measurement: of 330 failed edits across 45
# transcripts, 294 were against a file the same stage had already read. The
# model is not editing blind; byte-exact reproduction is simply the hard part,
# and it is a requirement `edit_artifact` invented rather than one the task has.
# ---------------------------------------------------------------------------

from app.tools.repository import replace_approved_lines


def test_a_line_range_needs_no_transcription(workspace):
    target = workspace / "p" / "g.py"
    target.write_text("def add(a, b):\n    return a + b\n\nprint(add(1, 2))\n", encoding="utf-8")

    result = replace_approved_lines(workspace, "p/g.py", 2, 2, "    return a - b")

    assert result["status"] == "edited"
    assert target.read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a - b\n\nprint(add(1, 2))\n"
    )


def test_replacing_a_range_spanning_several_lines(workspace):
    target = workspace / "p" / "h.go"
    target.write_text("package main\n\nfunc Add(a, b int) int {\n\treturn a + b\n}\n", encoding="utf-8")

    replace_approved_lines(workspace, "p/h.go", 3, 5, "func Add(a, b int) int { return a - b }")

    assert target.read_text(encoding="utf-8") == (
        "package main\n\nfunc Add(a, b int) int { return a - b }\n"
    )


def test_an_empty_replacement_deletes_the_range(workspace):
    target = workspace / "p" / "i.rb"
    target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")

    replace_approved_lines(workspace, "p/i.rb", 2, 2, "")

    assert target.read_text(encoding="utf-8") == "a = 1\nc = 3\n"


def test_a_stale_line_number_is_refused_rather_than_applied(workspace):
    target = workspace / "p" / "j.py"
    target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(workspace, "p/j.py", 2, 2, "x", expect_start="a = 1")

    assert "numbering has moved" in str(caught.value)
    assert target.read_text(encoding="utf-8") == "a = 1\nb = 2\nc = 3\n"


def test_the_expectation_ignores_whitespace(workspace):
    """A strict comparison would put back the requirement this tool removes."""
    target = workspace / "p" / "k.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")

    result = replace_approved_lines(
        workspace, "p/k.py", 2, 2, "    return 2", expect_start="return 1"
    )

    assert result["status"] == "edited"


def test_a_range_past_the_end_is_clamped_not_refused(workspace):
    target = workspace / "p" / "l.md"
    target.write_text("one\ntwo\n", encoding="utf-8")

    replace_approved_lines(workspace, "p/l.md", 2, 99, "TWO")

    assert target.read_text(encoding="utf-8") == "one\nTWO\n"


def test_a_start_past_the_end_is_refused_with_the_line_count(workspace):
    target = workspace / "p" / "m.md"
    target.write_text("one\ntwo\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(workspace, "p/m.md", 9, 9, "x")

    assert "2 lines" in str(caught.value)


def test_the_file_keeps_its_trailing_newline(workspace):
    target = workspace / "p" / "n.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")

    replace_approved_lines(workspace, "p/n.txt", 2, 2, "TWO")

    assert target.read_text(encoding="utf-8").endswith("\n")


@pytest.mark.parametrize(
    "name,body,line,replacement",
    [
        ("a.py", "def f():\n    return 1\n", 2, "    return 2"),
        ("a.go", "package m\nvar X = 1\n", 2, "var X = 2"),
        ("a.rs", "fn main() {}\nconst X: i32 = 1;\n", 2, "const X: i32 = 2;"),
        ("a.rb", "X = 1\nY = 2\n", 2, "Y = 3"),
        ("a.php", "<?php\n$x = 1;\n", 2, "$x = 2;"),
        ("a.java", "class A {}\n// x\n", 2, "// y"),
        ("a.md", "# Title\ntext\n", 2, "other text"),
    ],
)
def test_the_same_call_works_in_every_language(workspace, name, body, line, replacement):
    """No language is special: a line range means the same thing everywhere."""
    target = workspace / "p" / name
    target.write_text(body, encoding="utf-8")

    result = replace_approved_lines(workspace, f"p/{name}", line, line, replacement)

    assert result["status"] == "edited"
    assert replacement in target.read_text(encoding="utf-8")


def test_a_targeted_change_cannot_skip_the_guards(workspace):
    """Both tools share `_guard_a_targeted_change`; neither may lose a check."""
    with pytest.raises(RepositoryToolError):
        replace_approved_lines(workspace, "docs/product_intake.md", 1, 1, "x")
