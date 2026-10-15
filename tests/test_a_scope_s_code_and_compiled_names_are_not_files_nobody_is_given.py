"""Code and compiled names in a sprint's scope are not files nobody is given.

One run's lead plan was sent back twice - about 30 minutes - for "the sprint's
scope names process.env, server.js, store.js and no work order lists them",
with `server.ts` and `store.ts` in its work orders.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.analysis.integration_checks import files_named_in
from app.analysis.work_orders import _files_the_sprint_names_and_nobody_is_given


def test_an_environment_reference_or_a_call_is_not_a_file():
    named = files_named_in("Reads PORT from process.env; calls config.json() once; ships .env.example and app.ts", {"env", "ts"})

    assert "process.env" not in named and "config.json" not in named
    assert "app.ts" in named


def test_the_compiled_name_of_a_planned_source_file_is_that_file(tmp_path):
    tasks = [SimpleNamespace(files=["notes-api/src/server.ts", "notes-api/src/store.ts"])]
    scope = "server.js boots the app from store.js; routes.ts serves it; process.env holds PORT"

    unassigned = _files_the_sprint_names_and_nobody_is_given(scope, tasks, tmp_path, "notes-api")

    assert unassigned == ["routes.ts"]
