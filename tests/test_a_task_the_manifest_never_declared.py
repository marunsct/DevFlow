"""A runner asked for a name its manifest does not declare must be told what is.

`npm error Missing script: "test"` does not say which file was read, does not
say that the file declares nothing at all, and does not say that the fix is one
line in it. The names the runner would have accepted are in the workspace, and
nothing put the two together.

Measured on one run, which failed its first sprint. `package.json` was
written as `{"type": "module"}` - no `scripts` table - and the project's gating
command ran in all three test rounds:

    test_round_0  npm test  ->  npm error Missing script: "test"
    test_round_1  npm test  ->  npm error Missing script: "test"
    test_round_2  npm test  ->  npm error Missing script: "test"

Eighteen model turns across those rounds and not one added the script. The
sprint summary then reported one test case, zero passed.

The sibling of `_where_the_files_it_named_actually_are`, which answers the same
question about a path. Between them they cover both halves of what a failed
command can have been looking for: something the workspace does not have where
it looked, or a name the project never declared.

Nothing here is about npm. The shape - a runner, a name, and a file in the
workspace listing the names it accepts - is `make`, `just`, `rake`, `composer`,
`deno task`, `pdm run`, `tox -e` and `nox -s` as much as `npm run`, and each is
covered below.
"""

from __future__ import annotations

import json

import pytest

from app.tools.sandbox import (
    MAX_TASKS_NAMED,
    _the_task_a_command_asked_for,
    _the_tasks_this_project_defines,
)


@pytest.fixture
def a_workspace(tmp_path):
    """A workspace this test writes manifests into."""

    def _write(relative: str, content: str):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    _write.root = str(tmp_path)  # type: ignore[attr-defined]
    return _write


def _note(root, command, working_directory=None):
    return _the_tasks_this_project_defines(root, command, working_directory)


class TestTheManifestThatCostRunE980310bItsSprint:
    def test_a_manifest_with_no_scripts_at_all_is_named(self, a_workspace, tmp_path):
        a_workspace("app/package.json", json.dumps({"type": "module"}))

        note = _note(str(tmp_path), ["npm", "test"], "app")

        assert "app/package.json" in note
        assert "declares no scripts at all" in note

    def test_it_says_the_runner_is_not_refusing_the_command(self, a_workspace, tmp_path):
        """The distinction the npm error hides: nothing to look the name up in."""
        a_workspace("app/package.json", json.dumps({"type": "module"}))

        assert "nothing to look it up in" in _note(str(tmp_path), ["npm", "test"], "app")

    def test_it_names_the_entry_to_add(self, a_workspace, tmp_path):
        a_workspace("app/package.json", json.dumps({"type": "module"}))

        assert "`test` entry" in _note(str(tmp_path), ["npm", "test"], "app")

    def test_a_test_task_is_told_what_the_gates_measure(self, a_workspace, tmp_path):
        """Three rounds reported a suite while the command for it did not exist."""
        a_workspace("app/package.json", json.dumps({"type": "module"}))

        assert "Every gate in this pipeline" in _note(str(tmp_path), ["npm", "test"], "app")

    def test_a_build_task_is_not(self, a_workspace, tmp_path):
        """A `build` script is not what any gate measures, and saying so is false."""
        a_workspace("app/package.json", json.dumps({"scripts": {"test": "node --test"}}))

        note = _note(str(tmp_path), ["npm", "run", "build"], "app")

        assert "`build` is not one of the scripts" in note
        assert "Every gate in this pipeline" not in note


class TestNamingWhatIsThere:
    def test_the_declared_scripts_are_listed(self, a_workspace, tmp_path):
        a_workspace(
            "package.json",
            json.dumps({"scripts": {"build": "tsc", "dev": "vite", "lint": "eslint ."}}),
        )

        note = _note(str(tmp_path), ["npm", "test"])

        assert "`build`" in note and "`dev`" in note and "`lint`" in note

    def test_a_declared_task_says_nothing(self, a_workspace, tmp_path):
        """The command failed for some other reason, and this has no view on it."""
        a_workspace("package.json", json.dumps({"scripts": {"test": "node --test"}}))

        assert _note(str(tmp_path), ["npm", "test"]) == ""

    def test_a_long_list_is_capped_and_counted(self, a_workspace, tmp_path):
        scripts = {f"task{index}": "true" for index in range(MAX_TASKS_NAMED + 5)}
        a_workspace("package.json", json.dumps({"scripts": scripts}))

        note = _note(str(tmp_path), ["npm", "test"])

        assert "and 5 more" in note

    def test_the_manifest_is_found_above_the_directory_it_ran_in(
        self, a_workspace, tmp_path
    ):
        """Which is where every one of these runners looks for its own."""
        a_workspace("package.json", json.dumps({"scripts": {"build": "tsc"}}))
        (tmp_path / "src" / "deep").mkdir(parents=True)

        assert "`build`" in _note(str(tmp_path), ["npm", "test"], "src/deep")

    def test_the_search_stops_at_the_workspace_root(self, a_workspace, tmp_path):
        """A manifest outside the workspace is not this project's."""
        (tmp_path / "outside").write_text("x")
        root = tmp_path / "workspace"
        root.mkdir()

        assert _note(str(root), ["npm", "test"]) == ""


class TestEveryRunnerThatTakesATaskName:
    @pytest.mark.parametrize(
        "manifest,content,command,expected",
        [
            (
                "Makefile",
                "build:\n\tgcc -o app main.c\n\n.PHONY: build\ninstall: build\n\tcp app /usr/bin\n",
                ["make", "test"],
                "`build`",
            ),
            (
                "justfile",
                "build:\n    cargo build\n\nfmt target:\n    cargo fmt\n",
                ["just", "test"],
                "`fmt`",
            ),
            (
                "Rakefile",
                "task :build do\n  sh 'javac Main.java'\nend\n\ntask 'package' => :build do\nend\n",
                ["rake", "test"],
                "`build`",
            ),
            (
                "composer.json",
                json.dumps({"scripts": {"lint": "phpcs", "fix": "phpcbf"}}),
                ["composer", "run", "test"],
                "`lint`",
            ),
            (
                "deno.json",
                json.dumps({"tasks": {"dev": "deno run -A main.ts"}}),
                ["deno", "task", "test"],
                "`dev`",
            ),
            (
                "pyproject.toml",
                '[tool.pdm.scripts]\nlint = "ruff check"\n',
                ["pdm", "run", "test"],
                "`lint`",
            ),
            (
                "pyproject.toml",
                '[tool.poetry.scripts]\nserve = "app:main"\n',
                ["poetry", "run", "test"],
                "`serve`",
            ),
            (
                "pyproject.toml",
                '[tool.hatch.envs.default.scripts]\nfmt = "black ."\n',
                ["hatch", "run", "test"],
                "`fmt`",
            ),
            (
                "tox.ini",
                "[tox]\nenvlist = py311\n\n[testenv:py311]\ncommands = pytest\n",
                ["tox", "-e", "py312"],
                "`py311`",
            ),
            (
                "noxfile.py",
                "import nox\n\n@nox.session\ndef lint(session):\n    pass\n",
                ["nox", "-s", "tests"],
                "`lint`",
            ),
        ],
    )
    def test_the_names_it_declares_are_read(
        self, a_workspace, tmp_path, manifest, content, command, expected
    ):
        a_workspace(manifest, content)

        note = _note(str(tmp_path), command)

        assert expected in note, note

    def test_a_flag_glued_to_its_value_is_the_same_request(self, a_workspace, tmp_path):
        """`tox -epy311` and `tox -e py311` ask for the same environment."""
        a_workspace("tox.ini", "[testenv:py311]\ncommands = pytest\n")

        assert _note(str(tmp_path), ["tox", "-epy312"]) != ""
        assert _note(str(tmp_path), ["tox", "-epy311"]) == ""

    def test_the_noun_matches_the_runner(self, a_workspace, tmp_path):
        """A make target is not called a script, and a nox session is not either."""
        a_workspace("Makefile", "build:\n\ttrue\n")

        assert "targets" in _note(str(tmp_path), ["make", "test"])


class TestSayingNothingAboutCommandsThatNameNoTask:
    @pytest.mark.parametrize(
        "command",
        [
            ["node", "--test", "main.test.js"],
            ["npm", "install"],
            ["npm", "ci"],
            ["pnpm", "add", "-D", "vitest"],
            ["yarn", "install", "--frozen-lockfile"],
            ["npx", "playwright", "test"],
            ["python3", "-m", "pytest"],
            ["cargo", "test"],
            ["go", "test", "./..."],
            ["dotnet", "test"],
            ["./gradlew", "test"],
            ["git", "status"],
            [],
        ],
    )
    def test_it_is_silent(self, a_workspace, tmp_path, command):
        a_workspace("package.json", json.dumps({"type": "module"}))
        a_workspace("Makefile", "build:\n\ttrue\n")

        assert _note(str(tmp_path), command) == "", command

    def test_a_package_manager_subcommand_is_not_read_as_a_script(self):
        """`pnpm install` is pnpm's own, and reporting it as undefined is noise."""
        assert _the_task_a_command_asked_for(["pnpm", "install"]) is None

    def test_an_explicit_run_overrides_that(self, a_workspace, tmp_path):
        """A project may legitimately declare a script called `install`."""
        assert _the_task_a_command_asked_for(["npm", "run", "install"]) == (
            "install",
            ("package.json",),
        )


class TestNeverGettingInTheWay:
    def test_no_manifest_says_nothing(self, tmp_path):
        assert _note(str(tmp_path), ["npm", "test"]) == ""

    def test_an_unparseable_manifest_says_nothing(self, a_workspace, tmp_path):
        """Invalid JSON is its own reported problem, not this one."""
        a_workspace("package.json", "{not json")

        assert _note(str(tmp_path), ["npm", "test"]) == ""

    def test_a_manifest_that_is_not_an_object_says_nothing(self, a_workspace, tmp_path):
        a_workspace("package.json", "[1, 2, 3]")

        assert _note(str(tmp_path), ["npm", "test"]) == ""

    def test_a_missing_workspace_does_not_raise(self, tmp_path):
        assert _note(str(tmp_path / "gone"), ["npm", "test"]) == ""

    def test_a_working_directory_that_does_not_exist_falls_back_to_the_root(
        self, a_workspace, tmp_path
    ):
        a_workspace("package.json", json.dumps({"scripts": {"build": "tsc"}}))

        assert "`build`" in _note(str(tmp_path), ["npm", "test"], "no/such/place")


class TestItReachesTheCommandThatFailed:
    def test_a_failing_command_carries_the_note(self, a_workspace, tmp_path, monkeypatch):
        """The hint is worth nothing unless the stage that ran the command sees it."""
        from app.tools import sandbox

        a_workspace("package.json", json.dumps({"type": "module"}))
        monkeypatch.setattr(
            sandbox.SandboxExecutor,
            "_run",
            classmethod(lambda cls, *args, **kwargs: {"returncode": 1, "stdout": "", "stderr": 'Missing script: "test"'}),
        )

        outcome = sandbox.SandboxExecutor.execute(
            ["npm", "test"], str(tmp_path), role_name="testing_specialist"
        )

        assert "declares no scripts at all" in outcome.get("note", "")

    def test_a_passing_command_carries_no_note(self, a_workspace, tmp_path, monkeypatch):
        """Only a failure is a question about what the project declares."""
        from app.tools import sandbox

        a_workspace("package.json", json.dumps({"type": "module"}))
        monkeypatch.setattr(
            sandbox.SandboxExecutor,
            "_run",
            classmethod(lambda cls, *args, **kwargs: {"returncode": 0, "stdout": "ok", "stderr": ""}),
        )

        outcome = sandbox.SandboxExecutor.execute(
            ["npm", "test"], str(tmp_path), role_name="testing_specialist"
        )

        assert "declares no scripts" not in outcome.get("note", "")


class TestANameInTheWrongPlace:
    """`{"test": "node --test"}` is answered `Missing script: "test"`.

    True, and it reads as though the name were absent. It is present, one level
    too high. Found in the stored workspace of one run; the correction is
    not the one the plain missing-name note asks for.
    """

    def test_a_top_level_task_is_reported_as_misplaced(self, a_workspace, tmp_path):
        a_workspace("package.json", json.dumps({"test": "node --test ./tests"}))

        note = _note(str(tmp_path), ["npm", "test"])

        assert "does declare `test`" in note
        assert "top level" in note

    def test_it_asks_for_a_move_not_an_addition(self, a_workspace, tmp_path):
        a_workspace("package.json", json.dumps({"test": "node --test ./tests"}))

        note = _note(str(tmp_path), ["npm", "test"])

        assert "Move it into `scripts`" in note
        assert "declares no scripts at all" not in note

    def test_a_different_task_still_reads_as_absent(self, a_workspace, tmp_path):
        """Only the name that was asked for is looked for in the wrong place."""
        a_workspace("package.json", json.dumps({"test": "node --test"}))

        assert "does declare" not in _note(str(tmp_path), ["npm", "run", "build"])

    def test_a_non_string_value_is_not_a_misplaced_script(self, a_workspace, tmp_path):
        """`"build": {...}` is some other field that happens to share the name."""
        a_workspace("package.json", json.dumps({"build": {"outDir": "dist"}}))

        assert "does declare" not in _note(str(tmp_path), ["npm", "run", "build"])
