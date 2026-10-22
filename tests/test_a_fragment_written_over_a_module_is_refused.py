"""A few lines written over a whole module are refused on the first send.

The rewrite guard names a lost definition and lets the first such write land,
because dropping one is sometimes a deliberate refactor. Measured over the
stored runs: of 78 first writes it let land, the largest losses were 1 to 17
lines sent over a module, removing 13 to 54 definitions. One run's fix stage
wrote a four-line function over its 465-line `app.js`; every test failed and
the fix was reverted.
"""

from __future__ import annotations

import pytest

from app.tools.repository import RepositoryToolError, write_approved_artifact

MODULE = "".join(f"export function step{n}(value) {{\n  return value + {n};\n}}\n\n" for n in range(12))
FRAGMENT = "export function setMode(mode) {\n  current = mode;\n}\n"


@pytest.fixture(autouse=True)
def a_clean_tally():
    from app.agents import stage_memory
    from app.tools import repository

    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()
    repository._FRAGMENTS_OUTSIDE_A_RUN.clear()
    yield
    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()
    repository._FRAGMENTS_OUTSIDE_A_RUN.clear()


@pytest.fixture
def a_module(tmp_path):
    (tmp_path / "app").mkdir()
    write_approved_artifact(str(tmp_path), "app/logic.js", MODULE)
    return tmp_path


def test_the_fragment_is_refused_and_the_module_kept(a_module) -> None:
    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(str(a_module), "app/logic.js", FRAGMENT)

    message = str(refused.value)
    assert "would leave only what you sent" in message and "`edit_artifact`" in message
    assert "`step0`" in message
    assert (a_module / "app" / "logic.js").read_text().strip() == MODULE.strip()


def test_the_same_write_sent_again_is_a_decision(a_module) -> None:
    with pytest.raises(RepositoryToolError):
        write_approved_artifact(str(a_module), "app/logic.js", FRAGMENT)

    result = write_approved_artifact(str(a_module), "app/logic.js", FRAGMENT)

    assert (a_module / "app" / "logic.js").read_text().strip() == FRAGMENT.strip()
    assert "This write removes" in (result.get("note") or "")


def test_a_rewrite_of_comparable_size_is_only_noted(a_module) -> None:
    """A real refactor keeps most of the file's length; the rung below handles it."""
    rewritten = MODULE.replace("step0", "first").replace("step1(", "second(")

    result = write_approved_artifact(str(a_module), "app/logic.js", rewritten)

    assert "This write removes" in (result.get("note") or "")


def test_a_small_file_losing_few_names_is_not_a_fragment(tmp_path) -> None:
    (tmp_path / "app").mkdir()
    write_approved_artifact(str(tmp_path), "app/two.js", "export function a() {}\nexport function b() {}\n")

    result = write_approved_artifact(str(tmp_path), "app/two.js", "export function a() {}\n")

    assert (tmp_path / "app" / "two.js").read_text() == "export function a() {}\n"
    assert "This write removes" in (result.get("note") or "")
