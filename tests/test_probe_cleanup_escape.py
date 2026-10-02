"""The way out of the delete refusal has to actually work.

A test file is protected from deletion because one run deleted three real
suites as "temporary helper scripts". The refusal names an escape - rename it,
then delete the renamed file - for the agent that genuinely wrote a throwaway
probe.

That escape was built by taking `.test.` out of the filename, which is right
for `debug.test.mjs` and useless inside a `tests/` directory: `looks_like_a_test`
matches the directory too, so the renamed file was protected exactly as before.

One run walked into it. `specialist_ui_ux_0` wrote
`simple-to-do-list-app/tests/ui_test.js` as a probe, was refused the delete,
followed the instructions, moved it to `.../tests/ui_test.js.probe` and stopped
there - leaving a renamed corpse in the project it shipped. Had it tried the
second step it would have been refused again, by the same rule.

Every case here runs both steps for real, which is what "verified" has to mean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    _somewhere_this_rule_will_let_go_of,
    delete_approved_artifact,
    looks_like_a_test,
    move_approved_artifact,
    write_approved_artifact,
)

PROBES = [
    "proj/tests/ui_test.js",
    "proj/tests/tmp_check.js",
    "proj/__tests__/helper.js",
    "proj/spec/probe.mjs",
    "proj/debug.test.mjs",
    "proj/a.spec.ts",
]


@pytest.mark.parametrize("original", PROBES)
def test_the_destination_is_not_protected_by_the_same_rule(original: str) -> None:
    assert not looks_like_a_test(_somewhere_this_rule_will_let_go_of(original))


@pytest.mark.parametrize("original", PROBES)
def test_both_steps_of_the_escape_run(tmp_path: Path, original: str) -> None:
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "proj"}')
    (tmp_path / original).parent.mkdir(parents=True, exist_ok=True)
    # A probe that asserts: one that registers no test and asserts nothing is
    # deleted outright (`test_a_probe_named_like_a_test_can_be_removed`).
    (tmp_path / original).write_text("test('probe', () => { expect(1).toBe(1); });\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        delete_approved_artifact(tmp_path, original)
    message = str(caught.value)

    destination = _somewhere_this_rule_will_let_go_of(original)
    assert destination in message, "the refusal must name the destination it means"

    move_approved_artifact(tmp_path, original, destination)
    delete_approved_artifact(tmp_path, destination)

    assert not (tmp_path / destination).exists()
    assert not (tmp_path / original).exists()


def test_a_real_suite_is_still_protected(tmp_path: Path) -> None:
    """The reason the rule exists. One run deleted three passing suites."""
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "proj"}')
    write_approved_artifact(tmp_path, "proj/app.test.mjs", "import assert from 'node:assert';\nassert.ok(true);\n")

    with pytest.raises(RepositoryToolError):
        delete_approved_artifact(tmp_path, "proj/app.test.mjs")

    assert (tmp_path / "proj" / "app.test.mjs").exists()


def test_the_destination_is_never_a_file_that_is_already_there(tmp_path: Path) -> None:
    """A test beside the module it tests - `data.test.js` and `data.js` - is the
    commonest layout there is, and taking `.test.` out of the first names the
    second. One run's stage was told to move its test onto the product's own
    module and then delete it."""
    write_approved_artifact(tmp_path, "proj/package.json", '{"name": "proj"}')
    write_approved_artifact(tmp_path, "proj/src/data.js", "export const tasks = [];\n")
    write_approved_artifact(
        tmp_path, "proj/src/data.test.js", "test('probe', () => { expect(1).toBe(1); });\n"
    )

    with pytest.raises(RepositoryToolError) as caught:
        delete_approved_artifact(tmp_path, "proj/src/data.test.js")

    destination = _somewhere_this_rule_will_let_go_of("proj/src/data.test.js", tmp_path)
    assert destination == "proj/src/data.test.js.probe"
    assert f"'{destination}'" in str(caught.value)
    assert "to 'proj/src/data.js'" not in str(caught.value)

    # And the escape still works, with the product untouched by it.
    move_approved_artifact(tmp_path, "proj/src/data.test.js", destination)
    delete_approved_artifact(tmp_path, destination)
    assert (tmp_path / "proj" / "src" / "data.js").read_text(encoding="utf-8") == "export const tasks = [];\n"
