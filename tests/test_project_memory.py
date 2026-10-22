"""What each file is for, carried between stages that share no conversation.

Every stage is a fresh agent with an empty conversation. The only thing
carried between them is the digest, which listed names, line counts and
exported symbol *names* and stopped there.

Measured across the 50 stored transcripts, keying every `read_file` result on
the normalised path and the SHA-1 of the bytes returned:

    first time anyone in the run saw these bytes      2,162   54%
    a LATER STAGE, bytes an earlier stage already had 1,199   30%
    same stage, bytes it already had                    640   16%

The 16% already had two mechanisms aimed at it. The 30% had none, and that
number says what the index must carry: enough that a later stage does not
need the bytes. Two things were missing from a list of names - what the file
is FOR, and how to CALL it - and both are derived from the file, so no tool
gains an argument and no model is asked for anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.project_memory import (
    MEMORY_FILE,
    interface_of,
    note_for,
    purpose_of,
    record,
    who_changed,
)

# --- the purpose, in every language the harness builds in ------------------


@pytest.mark.parametrize(
    "name, text, expected",
    [
        (
            "server.mjs",
            "// server.mjs - Minimal static file server for Playwright testing.\n"
            "// Reads files from the directory where it is invoked.\n",
            "Minimal static file server for Playwright testing.",
        ),
        (
            "app.py",
            '"""The task model and every operation on it.\n\nMore detail.\n"""\n',
            "The task model and every operation on it.",
        ),
        (
            "Widget.java",
            "/**\n * Renders one row of the task list.\n * @param task the task\n */\n",
            "Renders one row of the task list.",
        ),
        ("main.go", "// Package main starts the HTTP server.\npackage main\n",
         "Package main starts the HTTP server."),
        ("lib.rs", "//! Parsing for the wire format.\n", "Parsing for the wire format."),
        ("index.html", "<!-- The single page the app runs in. -->\n<html></html>",
         "The single page the app runs in."),
        ("schema.sql", "-- Every table the product persists.\n",
         "Every table the product persists."),
        ("build.sh", "#!/bin/sh\n# Builds the release bundle.\n",
         "Builds the release bundle."),
        ("README.md", "# Task Manager\n\nA to-do list.\n", "Task Manager"),
    ],
)
def test_a_purpose_is_read_from_the_file_itself(name: str, text: str, expected: str):
    assert purpose_of(text, name) == expected


@pytest.mark.parametrize(
    "name, text",
    [
        ("app.js", "// app.js\nexport function go() {}\n"),
        ("app.js", "// app\n"),
        ("style.css", "/* style.css */\nbody{}\n"),
        ("lib.js", "// Copyright 2026 Someone\n// SPDX-License-Identifier: MIT\n"),
        ("a.js", "// eslint-disable-next-line\nconst x = 1;\n"),
        ("b.py", "# -*- coding: utf-8 -*-\nimport os\n"),
        ("plain.js", "const x = 1;\n"),
        ("empty.js", ""),
    ],
)
def test_nothing_is_better_than_a_wrong_purpose(name: str, text: str):
    """A stage acts on this line INSTEAD of reading the file.

    A label, a licence header or a linter pragma says nothing about what the
    file does, and a wrong purpose is worse than none precisely because it is
    believed.
    """
    assert purpose_of(text, name) == ""


def test_a_purpose_is_one_sentence_and_not_a_paragraph():
    text = "// Does the first thing. Then it does a second thing entirely.\n"

    assert purpose_of(text, "a.js") == "Does the first thing."


def test_a_very_long_header_is_cut_rather_than_carried():
    text = "// " + ("word " * 200) + "\n"

    assert len(purpose_of(text, "a.js")) <= 140


def test_a_purpose_survives_a_file_that_cannot_be_parsed():
    """Never raises: an index that throws is worse than one that is empty."""
    assert purpose_of("\x00\xff not text at all", "a.js") == ""


# --- the interface, in every language --------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("export function createTask(title, dueDate) {}", "createTask(title, dueDate)"),
        ("export const toggleTask = (id) => {};", "toggleTask(id)"),
        ("def save(data, *, force=False):\n    pass", "save(data, *, force=False)"),
        ("func Serve(addr string) error {}", "Serve(addr string)"),
        ("pub fn parse(input: &str) -> Result<T> {}", "parse(input: &str)"),
        ("public void render(Task task) {}", "render(Task task)"),
        ("class Store {}", "Store"),
        ("interface Repo {}", "Repo"),
    ],
)
def test_a_signature_says_what_a_name_cannot(text: str, expected: str):
    assert expected in interface_of(text)


def test_a_keyword_is_not_mistaken_for_a_function():
    surface = interface_of("if (ready) {}\nfor (;;) {}\nswitch (x) {}\nwhile (a) {}")

    assert surface == ""


def test_the_interface_is_capped():
    text = "\n".join(f"function f{n}(a) {{}}" for n in range(40))

    assert interface_of(text).count("(") <= 8


def test_a_very_long_parameter_list_is_cut():
    text = "function go(" + ", ".join(f"argument{n}" for n in range(30)) + ") {}"

    assert "..." in interface_of(text)


# --- who last changed it ---------------------------------------------------


def test_the_authoring_stage_is_remembered(tmp_path: Path):
    record(tmp_path, "app/main.go", "specialist_backend_0")

    assert who_changed(tmp_path, "app/main.go") == "specialist_backend_0"


def test_one_file_however_the_path_is_spelled(tmp_path: Path):
    """The same normalisation every other guard uses. See `the_same_place`."""
    record(tmp_path, "/app/main.go", "specialist_backend_0")

    assert who_changed(tmp_path, "app/main.go") == "specialist_backend_0"
    assert who_changed(tmp_path, "./app/main.go") == "specialist_backend_0"


def test_the_last_stage_to_write_is_the_one_recorded(tmp_path: Path):
    record(tmp_path, "app/main.go", "specialist_backend_0")
    record(tmp_path, "app/main.go", "test_round_0")

    assert who_changed(tmp_path, "app/main.go") == "test_round_0"


def test_a_write_outside_a_run_does_not_erase_the_author(tmp_path: Path):
    """`_stage_from_config` returns "" outside a graph run, and "" is not a stage."""
    record(tmp_path, "app/main.go", "specialist_backend_0")
    record(tmp_path, "app/main.go", "")

    assert who_changed(tmp_path, "app/main.go") == "specialist_backend_0"


def test_an_unwritable_workspace_does_not_fail_the_write(tmp_path: Path):
    record(tmp_path / "does" / "not" / "exist", "app/main.go", "a_stage")

    assert who_changed(tmp_path, "app/main.go") == ""


def test_a_corrupt_memory_file_is_a_fresh_start(tmp_path: Path):
    (tmp_path / MEMORY_FILE).write_text("{not json", encoding="utf-8")

    assert who_changed(tmp_path, "app/main.go") == ""
    record(tmp_path, "app/main.go", "a_stage")
    assert who_changed(tmp_path, "app/main.go") == "a_stage"


def test_a_note_gathers_all_of_it(tmp_path: Path):
    record(tmp_path, "app/app.js", "specialist_backend_2")

    note = note_for(
        tmp_path,
        "app/app.js",
        "/** The task model. */\nexport function createTask(title) {}\n",
    )

    assert note.purpose == "The task model."
    assert note.interface == "createTask(title)"
    assert note.changed_by == "specialist_backend_2"
    assert note.lines == 3


# --- what a stage actually sees --------------------------------------------


def test_the_digest_carries_purpose_interface_and_author(tmp_path: Path):
    from app.agents.workspace_digest import render_workspace_digest

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "app.js").write_text(
        "/**\n * The task model and every operation on it.\n */\n"
        "export function createTask(title, dueDate) {}\n",
        encoding="utf-8",
    )
    record(tmp_path, "app/app.js", "specialist_backend_2")

    digest = render_workspace_digest(tmp_path)

    assert "The task model and every operation on it." in digest
    assert "createTask(title, dueDate)" in digest
    assert "written by specialist_backend_2" in digest


def test_the_memory_file_is_never_shown_to_a_stage(tmp_path: Path):
    """It is the harness's bookkeeping, and it appeared at the top of the list."""
    from app.agents.workspace_digest import render_workspace_digest
    from app.tools.repository import list_repository_files

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    record(tmp_path, "app/app.js", "a_stage")

    assert MEMORY_FILE not in render_workspace_digest(tmp_path)
    assert not any(MEMORY_FILE in name for name in list_repository_files(tmp_path))


def test_a_file_with_neither_costs_no_extra_lines(tmp_path: Path):
    from app.agents.workspace_digest import render_workspace_digest

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "style.css").write_text("body{}\n", encoding="utf-8")

    digest = render_workspace_digest(tmp_path)

    assert "app/style.css" in digest
    assert digest.count("app/style.css") == 1


class TestConcurrentRecording:
    """Parallel execution mode has several stages writing this file at once.

    One entry is recorded by reading the whole file, changing one key and
    writing it all back. With one stage running at a time that is sound, and it
    was sound for as long as that was the only mode. A milestone fanned out to
    three specialists has three of them recording writes concurrently.
    """

    def test_no_entry_is_lost_when_stages_record_at_the_same_time(self, tmp_path):
        """Each worker reads before the others' changes land; one entry wins.

        Without the lock this loses entries in proportion to how much work runs
        in parallel, and what it loses is the record of who changed a file -
        which is what the digest uses to tell a stage that another stage has
        already been here.
        """
        import threading

        from app.analysis.project_memory import record, who_changed

        (tmp_path / "app").mkdir()
        names = [f"app/file{index}.js" for index in range(24)]
        for name in names:
            (tmp_path / name).write_text("//\n", encoding="utf-8")

        barrier = threading.Barrier(len(names))

        def write(name: str) -> None:
            barrier.wait()
            record(tmp_path, name, stage=f"stage_for_{name}")

        threads = [threading.Thread(target=write, args=(name,)) for name in names]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        missing = [name for name in names if not who_changed(tmp_path, name)]
        assert not missing, f"{len(missing)} of {len(names)} entries were lost: {missing[:5]}"

    def test_a_reader_never_sees_a_half_written_file(self, tmp_path):
        """`write_text` truncates first, and every reader treats unreadable as empty.

        So a read landing inside a write did not degrade - it reported that the
        project had no memory at all, which is the reading that makes a stage
        re-read files another stage had already described.
        """
        import json
        import threading

        from app.analysis.project_memory import MEMORY_FILE, record

        (tmp_path / "app").mkdir()
        for index in range(40):
            (tmp_path / f"app/file{index}.js").write_text("//\n", encoding="utf-8")

        stop = threading.Event()
        damaged: list[str] = []

        def read_repeatedly() -> None:
            path = tmp_path / MEMORY_FILE
            while not stop.is_set():
                try:
                    raw = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if not raw:
                    continue
                try:
                    json.loads(raw)
                except ValueError:
                    damaged.append(raw[:40])

        reader = threading.Thread(target=read_repeatedly)
        reader.start()
        try:
            for index in range(40):
                record(tmp_path, f"app/file{index}.js", stage="writer")
        finally:
            stop.set()
            reader.join()

        assert not damaged, f"a reader saw {len(damaged)} half-written states, e.g. {damaged[:1]}"
