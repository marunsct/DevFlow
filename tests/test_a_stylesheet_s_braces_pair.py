"""A stylesheet with an unpaired brace is refused, like a file that will not parse.

Measured on one completed run: `style.css` shipped with a stray `}` after its
list rule. A browser reads that as the start of the next rule's selector, drops
the rule, and says nothing; every test passed and the review accepted it.
"""

from __future__ import annotations

import pytest

from app.analysis.syntax_balance import structural_problem
from app.tools.repository import RepositoryToolError, edit_approved_artifact, write_approved_artifact

SOUND = """\
#task-list {
  list-style: none;
  padding: 0;
}

#task-list li { background: white; }

@media (max-width: 599px) {
  #task-list li { display: block; }
}
"""

A_STRAY_CLOSER = SOUND.replace("  padding: 0;\n}\n", "  padding: 0;\n}\n}\n")


def test_a_closer_with_nothing_open_is_named_with_its_line() -> None:
    problem = structural_problem("app/style.css", A_STRAY_CLOSER)

    assert problem and "the '}' on line 5 closes nothing" in problem
    assert "drops the rule that follows" in problem


def test_a_block_never_closed_is_named_with_its_line() -> None:
    problem = structural_problem("app/style.css", SOUND.rstrip()[:-1])

    assert problem and "the '{' opened on line 8 is never closed" in problem


def test_a_sound_stylesheet_has_no_problem() -> None:
    assert structural_problem("app/style.css", SOUND) is None


def test_braces_in_strings_and_comments_are_not_counted() -> None:
    tricky = SOUND + '\n/* a } in a comment { */\n.note::before { content: "}"; }\n'

    assert structural_problem("app/style.css", tricky) is None


def test_the_write_is_refused(tmp_path) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(tmp_path, "app/style.css", A_STRAY_CLOSER)

    assert "closes nothing" in str(caught.value)
    assert not (tmp_path / "app" / "style.css").exists()


def test_an_edit_that_unpairs_them_is_refused(tmp_path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "style.css").write_text(SOUND, encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(tmp_path, "app/style.css", "  padding: 0;\n}", "  padding: 0;\n}\n}")

    assert (tmp_path / "app" / "style.css").read_text(encoding="utf-8") == SOUND


def test_a_missing_colon_the_count_cannot_see_is_found_by_the_grammar() -> None:
    """Measured over the 122 stored stylesheets: the CSS grammar flagged two,
    both real - one this test's brace, and `backgroundrgba(...)`, which a
    browser drops without a word and no brace count can see."""
    from app.analysis.syntax_balance import structural_problem

    problem = structural_problem("styles.css", ".modal { display: flex; backgroundrgba(0,0,0,.5); }\n")
    assert problem is not None and "does not parse as CSS" in problem and "line 1" in problem
    modern = (
        "@media (max-width: 600px) { .a { display: none } }\n"
        ".b::before { content: \"}\" }\n:root { --gap: 4px }\n"
        "@container (min-width: 400px) { .c { color: red } }\n.d { &:hover { color: red } }\n"
    )
    assert structural_problem("styles.css", modern) is None
