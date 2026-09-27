"""The "no arbitrary code" boundary has to hold in every language, not two.

`_FORBIDDEN_ARGS` refuses an argument that hands a program its code instead of
a file. Measured 2026-09-27 by calling `validate_command` once per entry in
`TOOLCHAINS` with `.project-stack` set to that language: `node -e` and
`python3 -c` were refused, and `ruby -e`, `php -r`, `elixir -e`, `scala -e`,
`rake -e`, `mix run -e`, `bundle exec`, `poetry run`, `uv run`, `composer exec`
and `gradle -I` were all permitted. The allowlist is the security boundary, so
each of those walked straight through it - `bundle exec <anything>` runs a
program no role was granted, exactly as `npm exec` does, and that one was
already blocked.

A stack this harness has never been run on is the case these tests are for, so
they are written against the toolchain table rather than against a list of
languages, and a language added to that table is covered without a second edit.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def _refusal(command: list[str], language: str, tmp_path: Path) -> str | None:
    """The refusal for `command` under a project pinned to `language`, or None."""
    from app.tools.sandbox import STACK_MARKER, CommandNotAllowed, validate_command

    (tmp_path / STACK_MARKER).write_text(language, encoding="utf-8")
    try:
        validate_command(command, role_name="backend_specialist", repo_root=tmp_path)
    except CommandNotAllowed as refused:
        return str(refused)
    return None


#: One "the code is in this argument" command per language that has such a form.
#: `go run .` and `cargo run` are deliberately absent: they compile and run the
#: project in front of them, which is a build step.
EVALUATES_AN_ARGUMENT = (
    ("python", ["python3", "-c", "print(1)"]),
    ("javascript", ["node", "-e", "console.log(1)"]),
    ("javascript", ["node", "--eval", "console.log(1)"]),
    ("javascript", ["node", "-p", "1"]),
    ("ruby", ["ruby", "-e", "puts 1"]),
    ("ruby", ["rake", "-e", "puts 1"]),
    ("php", ["php", "-r", "echo 1;"]),
    ("elixir", ["elixir", "-e", "IO.puts 1"]),
    ("elixir", ["mix", "run", "-e", "IO.puts 1"]),
    ("scala", ["scala", "-e", "println(1)"]),
)


@pytest.mark.parametrize(("language", "command"), EVALUATES_AN_ARGUMENT)
def test_code_in_an_argument_is_refused_in_every_language(
    language: str, command: list[str], tmp_path: Path
) -> None:
    refusal = _refusal(command, language, tmp_path)

    assert refusal is not None, (
        f"{' '.join(command)} was permitted for a {language} project: the "
        "arbitrary-code boundary does not hold for this language"
    )
    assert "arbitrary code" in refusal


def test_npm_exec_is_still_refused(tmp_path: Path) -> None:
    """The one `exec`-style entry that predates this, unchanged."""
    assert _refusal(["npm", "exec", "whatever"], "javascript", tmp_path) is not None


def test_the_exec_hatch_is_not_closed_in_other_languages(tmp_path: Path) -> None:
    """`bundle exec` and friends stay permitted, deliberately.

    Refusing them looks like the obvious symmetry with `npm exec` and is not
    one. Blocking `npm exec` never closed that hole - `npx <anything>` is
    permitted and does the same thing - so refusing the others would not
    tighten the boundary, only make every non-JavaScript language stricter than
    JavaScript. This test exists so the next person to notice the asymmetry
    finds the measurement instead of repeating it.
    """
    assert _refusal(["npx", "whatever-i-like"], "javascript", tmp_path) is None, (
        "if `npx <anything>` is ever refused, the reasoning below changes and "
        "the `exec` hatch is worth closing everywhere"
    )
    for language, command in (
        ("ruby", ["bundle", "exec", "rspec"]),
        ("python", ["poetry", "run", "pytest"]),
        ("php", ["composer", "exec", "phpunit"]),
    ):
        assert _refusal(command, language, tmp_path) is None, (
            f"{' '.join(command)} is refused while `npx <anything>` is not"
        )


@pytest.mark.parametrize(
    "command",
    (
        ["gradle", "-I", "init.gradle", "build"],
        ["gradle", "--build-file", "other.gradle"],
    ),
)
def test_a_build_pointed_at_a_foreign_file_is_refused(
    command: list[str], tmp_path: Path
) -> None:
    """`make -f` was refused and `gradle -b` was not, for the same shape."""
    assert _refusal(command, "java", tmp_path) is not None


@pytest.mark.parametrize(
    ("language", "command"),
    (
        ("go", ["go", "run", "."]),
        ("rust", ["cargo", "run"]),
        # The ordinary entry points must survive: only "here is the code" and
        # "run anything" are refused, not the package manager itself.
        ("javascript", ["npm", "run", "test"]),
        ("python", ["pip", "install", "-r", "requirements.txt"]),
        ("java", ["gradle", "test"]),
        ("ruby", ["rake", "test"]),
        ("php", ["composer", "install"]),
        ("elixir", ["mix", "test"]),
        # `rspec` and `rake` reach their project through bundler, and `pytest`
        # through poetry's virtualenv. Refusing `bundle exec` and `poetry run`
        # took all three away, which is why neither is refused. (A *server*
        # behind either is still refused, by the long-running-command guard and
        # with its own advice - that is a different rule and is left alone.)
        ("ruby", ["bundle", "exec", "rspec"]),
        ("ruby", ["bundle", "exec", "rake", "db:migrate"]),
        ("python", ["poetry", "run", "pytest", "-q"]),
        # The advice each eval refusal gives has to be a command that runs.
        ("ruby", ["ruby", "verify.rb"]),
        ("php", ["php", "verify.php"]),
        ("elixir", ["elixir", "verify.exs"]),
        ("scala", ["scala", "Verify.scala"]),
    ),
)
def test_a_real_build_step_still_runs(
    language: str, command: list[str], tmp_path: Path
) -> None:
    """The cost of over-blocking is a language that cannot be built at all."""
    refusal = _refusal(command, language, tmp_path)

    assert refusal is None or "not permitted for role" in refusal, (
        f"{' '.join(command)} is how a {language} project is built, and it was "
        f"refused as a forbidden argument: {refusal}"
    )


def test_every_refused_argument_says_what_to_do_instead() -> None:
    """Advice that does not fit the command is worse than none.

    "Put the code in a file" is right for `ruby -e` and nonsense for
    `bundle exec rspec`, whose answer is to run `rspec`.
    """
    from app.tools.sandbox import _FORBIDDEN_ARGS, _WHY_THE_ARGUMENT_IS_REFUSED

    missing = sorted(set(_FORBIDDEN_ARGS) - set(_WHY_THE_ARGUMENT_IS_REFUSED))

    assert not missing, (
        f"{missing} refuse an argument without saying which advice fits, so "
        "they fall back to advice written for a different shape"
    )


def test_exec_style_refusals_do_not_send_an_agent_to_write_a_file() -> None:
    from app.tools.sandbox import _what_to_do_with_that_argument

    advice = _what_to_do_with_that_argument(
        "npm", ["npm", "exec", "--", "sh"], None, frozenset({"node", "npm"})
    )

    assert "delete_artifact" not in advice
    assert "directly" in advice


def test_every_language_can_run_its_own_suite_directly() -> None:
    """Every `exec`-style refusal must leave a permitted way to run the tests.

    The condition for refusing one of these at all: the direct equivalent is
    already on the allowlist, so nothing is lost. It is the condition
    `bundle exec` failed, and the reason that entry was dropped.
    """
    from app.tools.sandbox import _FORBIDDEN_ARGS, _WHY_THE_ARGUMENT_IS_REFUSED, TOOLCHAINS

    runners = {
        "ruby": "rspec",
        "python": "pytest",
        "php": "phpunit",
        "javascript": "npm",
        "typescript": "npm",
        "elixir": "mix",
    }
    for language, tools in TOOLCHAINS.items():
        blocked = {
            name
            for name in tools & set(_FORBIDDEN_ARGS)
            if _WHY_THE_ARGUMENT_IS_REFUSED.get(name) == "any_program"
        }
        if not blocked:
            continue
        runner = runners.get(language)
        assert runner is not None, (
            f"{language} has {sorted(blocked)} refused and no direct test "
            "runner recorded here, so the refusal may have no way around it"
        )
        assert runner in tools, (
            f"{language} loses {sorted(blocked)} and its toolchain does not "
            f"include `{runner}`, so its suite cannot be run at all"
        )


def test_the_brief_names_the_refusal_before_a_stage_trips_it(tmp_path: Path) -> None:
    """Three parallel specialists each sent the same refused `node -e`.

    The run-scoped counter told the second and third it had already been
    refused, which cannot help: they run in parallel, so their commands were
    formed before the first refusal existed. Only the brief reaches them.
    """
    from app.agents.specialists import describe_stack

    class Stack:
        language = "JavaScript"
        framework = "None (Vanilla HTML/CSS/JavaScript)"
        frontend_framework = ""
        database = "Browser localStorage"
        testing_framework = "node:test"
        additional_tools: tuple[str, ...] = ()

    described = describe_stack(Stack())

    assert "node -e" in described, (
        "a JavaScript specialist is not told that `node -e` is refused until it "
        "has already spent a call on one"
    )
    assert "delete_artifact" in described


def test_the_brief_only_names_programs_this_image_has() -> None:
    """The mistake `test_advice_names_installed_programs` was written for.

    A brief naming `pnpm` or `yarn` sends a stage to a program the image does
    not have, and being refused for the wrong reason is worse than not knowing.
    """
    from app.agents.specialists import _no_code_on_the_command_line

    class Stack:
        language = "Ruby"
        framework = "Rails"
        frontend_framework = ""
        testing_framework = "rspec"

    note = _no_code_on_the_command_line(Stack())

    for named in ("ruby", "rake"):
        if f"`{named} " in note:
            assert shutil.which(named), (
                f"the brief warns about `{named}`, which is not on PATH here"
            )


def test_a_stack_with_no_interpreter_gets_no_note() -> None:
    """An empty stack, or one whose language has no eval form, adds nothing."""
    from app.agents.specialists import _no_code_on_the_command_line

    class Unknown:
        language = "COBOL"
        framework = ""

    assert _no_code_on_the_command_line(Unknown()) == ""
