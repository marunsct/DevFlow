"""A suite file the runner skips only because of its name's separator is renamed to the runner's pattern by the harness.

Measured on one run: QA wrote `delete_spec.js`, `getid_spec.js` and three more where the runner collects `*.spec.js`.
Told each time "the file's name is the reason", it wrote correctly named copies of three and left two, and after five
rounds the run failed: "the acceptance suite proves nothing". A rename needs no model.
"""
from __future__ import annotations

from app.acceptance import suite
from app.stacks import contract, pack_named


def _suite(tmp_path, files):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(text)
    return tmp_path, folder


def test_a_file_off_only_by_its_separator_is_renamed(tmp_path):
    root, folder = _suite(tmp_path, {"delete_spec.js": "test('[AC-5] deletes', async () => {});\n"})

    renamed = suite.rename_files_the_runner_skips(root)

    assert (folder / "delete.spec.js").is_file() and not (folder / "delete_spec.js").exists()
    assert renamed == ["notes/acceptance/delete_spec.js -> notes/acceptance/delete.spec.js"]


def test_one_whose_right_name_is_taken_is_left(tmp_path):
    root, folder = _suite(tmp_path, {"ac10_spec.js": "x", "ac10.spec.js": "y"})

    assert suite.rename_files_the_runner_skips(root) == []
    assert (folder / "ac10_spec.js").read_text() == "x" and (folder / "ac10.spec.js").read_text() == "y"


def test_collected_and_unrelated_files_are_left(tmp_path):
    root, folder = _suite(tmp_path, {"notes.spec.js": "x", "service.cjs": "y", "helpers.js": "z"})

    assert suite.rename_files_the_runner_skips(root) == []


def test_the_review_renames_before_it_judges():
    import inspect

    from app.graph import acceptance_nodes

    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert source.index("rename_files_the_runner_skips(") < source.index("suite.run(root)")
