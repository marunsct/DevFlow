"""A manifest whose `test` script leaves suites on disk unrun is refused.

`_the_test_command_will_not_run_this` says so at the write of each test file,
and that note is the right first response. One run delivered it twenty-
seven times across ten stages and still ended with

    "test": "node --test test_filter.mjs"

beside `app.test.mjs` and `filter.test.mjs`. Eleven of the fifty-four readable
stored manifests strand a suite this way. A note ignored twenty-seven times is
not a note that needs rewording - the same escalation the no-op write and the
edit that goes backwards already settled.

The refusal has to stay narrow, and most of what follows guards that: two of
its first thirteen hits were a jest config read as a suite and a shell glob
read as a literal filename.
"""

from __future__ import annotations

import json

import pytest

from app.tools.repository import RepositoryToolError, write_approved_artifact

A_SUITE = "import { test } from 'node:test';\ntest('x', () => {});\n"


def _project(tmp_path, *test_files: str, **contents: str):
    (tmp_path / "proj").mkdir()
    for name in test_files:
        write_approved_artifact(tmp_path, f"proj/{name}", A_SUITE)
    for name, body in contents.items():
        write_approved_artifact(tmp_path, f"proj/{name.replace('__', '.')}", body)
    return tmp_path


def _manifest(tmp_path, command: str):
    return write_approved_artifact(
        tmp_path,
        "proj/package.json",
        json.dumps({"name": "p", "scripts": {"test": command}}),
    )


def test_a_command_naming_one_of_three_suites_is_refused(tmp_path):
    _project(tmp_path, "app.test.mjs", "filter.test.mjs", "test_filter.mjs")
    with pytest.raises(RepositoryToolError) as refusal:
        _manifest(tmp_path, "node --test test_filter.mjs")
    assert "app.test.mjs" in str(refusal.value)
    assert "filter.test.mjs" in str(refusal.value)
    # The way out has to be in the refusal, or the agent guesses.
    assert "node --test" in str(refusal.value)


def test_a_command_naming_every_suite_is_written(tmp_path):
    _project(tmp_path, "app.test.mjs", "filter.test.mjs")
    _manifest(tmp_path, "node --test app.test.mjs filter.test.mjs")


def test_a_chain_that_still_misses_one_is_refused(tmp_path):
    """One run ran three suites with `&&` and stranded three more."""
    _project(tmp_path, "a.test.mjs", "b.test.mjs", "c.test.mjs")
    with pytest.raises(RepositoryToolError) as refusal:
        _manifest(tmp_path, "node --test a.test.mjs && node --test b.test.mjs")
    assert "c.test.mjs" in str(refusal.value)


def test_a_discovering_command_is_never_refused(tmp_path):
    _project(tmp_path, "app.test.mjs", "filter.test.mjs")
    _manifest(tmp_path, "node --test")


def test_a_glob_is_the_shells_discovery_and_not_a_name(tmp_path):
    """One run ran `node --test *.test.mjs`.

    Read literally the pattern is a filename nothing matches, so every suite
    it would have run came back stranded - a refusal of a working command.
    """
    _project(tmp_path, "app.test.mjs", "data.test.mjs")
    _manifest(tmp_path, "node --test *.test.mjs")


def test_a_config_flag_does_not_name_a_suite(tmp_path):
    """One run ran `npx jest --config=jest.config.js`.

    `jest.config.js` is a configuration file, and jest with no pattern
    searches the project - nothing is stranded.
    """
    _project(tmp_path, "app.test.mjs", jest__config__js="module.exports = {};")
    _manifest(tmp_path, "npx jest --config=jest.config.js")


def test_a_runner_that_imports_the_suites_strands_nothing(tmp_path):
    """One run's `run-tests.mjs` imported its suites; naming it is enough."""
    _project(tmp_path, "add.test.mjs", "filter.test.mjs")
    write_approved_artifact(
        tmp_path,
        "proj/run-tests.mjs",
        "import './add.test.mjs';\nimport './filter.test.mjs';\n",
    )
    _manifest(tmp_path, "node --test run-tests.mjs")


def test_a_runner_is_not_credited_with_suites_it_does_not_import(tmp_path):
    _project(tmp_path, "add.test.mjs", "orphan.test.mjs")
    write_approved_artifact(tmp_path, "proj/run-tests.mjs", "import './add.test.mjs';\n")
    with pytest.raises(RepositoryToolError) as refusal:
        _manifest(tmp_path, "node --test run-tests.mjs")
    assert "orphan.test.mjs" in str(refusal.value)
    assert "add.test.mjs" not in str(refusal.value)


def test_a_manifest_written_before_the_suites_exist_is_untouched(tmp_path):
    _project(tmp_path)
    _manifest(tmp_path, "node --test app.test.mjs")


def test_a_leftover_scratch_suite_does_not_block_the_manifest(tmp_path):
    """`tmp_flow_test.mjs` is debris, not a suite the project owes a run."""
    _project(tmp_path, "app.test.mjs", "tmp_flow_test.mjs")
    _manifest(tmp_path, "node --test app.test.mjs")


def test_a_manifest_with_no_test_script_is_untouched(tmp_path):
    _project(tmp_path, "app.test.mjs")
    write_approved_artifact(
        tmp_path, "proj/package.json", json.dumps({"name": "p", "scripts": {}})
    )


def test_the_check_itself_never_fails_a_write(tmp_path):
    """A manifest that is not JSON is already refused for being unreadable.

    This check must not be what raises - it has nothing to say about a file it
    cannot parse, and a check that throws on malformed input would turn every
    such write into the wrong error.
    """
    from app.tools.repository import _refuse_a_test_script_that_strands_suites

    _project(tmp_path, "app.test.mjs")
    for unreadable in ("not json at all", "", "[]", '{"scripts": "not an object"}'):
        _refuse_a_test_script_that_strands_suites(
            tmp_path / "proj" / "package.json", unreadable
        )


def test_only_package_json_is_checked(tmp_path):
    """A `test` script in some other JSON file is not a manifest."""
    _project(tmp_path, "app.test.mjs", "other.test.mjs")
    write_approved_artifact(
        tmp_path,
        "proj/config.json",
        json.dumps({"scripts": {"test": "node --test app.test.mjs"}}),
    )
