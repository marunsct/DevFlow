"""Two defects that quote one compiler error are one cause, given to one fixer.

Measured on one C# run: "the unit tests fail" quoted `Program.cs(297,84): error CS0721`, and "the product does not
start" carried the same error in what the product's own start wrote. They went to two fixers in parallel, which took
turns at the one file - each refused while the other changed it - for half an hour.
"""

from __future__ import annotations

from app.acceptance.start_output import START_MARK
from app.graph import workflow
from workflow_nodes import reported

ERROR = "/workspace/notes-api/src/App/Program.cs(297,84): error CS0721: 'NoteStore': static types cannot be used as parameters"


def _unit(error: str = ERROR):
    return reported(f"The unit tests fail. It says:\n{error}\n The runner's output ends:\n{error}")


def _start(error: str = ERROR):
    return reported("The product does not start for the acceptance suite, so no test can reach it.",
                    actual_behavior=f"{START_MARK} (`sh start.sh`): it stopped by itself with exit code 1. It wrote:\n"
                                    f"{error.replace('notes-api', '.harness/as-delivered/product')}\nThe build failed.")


def test_the_start_that_failed_on_the_unit_run_s_compiler_error_joins_it():
    merged = workflow._one_defect_per_cause([_unit(), _start()])
    assert len(merged) == 1 and merged[0].description.startswith("The unit tests fail.")


def test_errors_at_other_places_stay_two_defects():
    other = "/workspace/notes-api/src/App/Store.cs(12,5): error CS0103: The name 'x' does not exist"
    assert len(workflow._one_defect_per_cause([_unit(), _start(other)])) == 2


def test_a_location_on_a_line_that_is_not_an_error_joins_nothing():
    assert workflow._error_locations("at main (server.go:10)\nok  notes_api 0.4s") == set()
    assert workflow._error_locations("server.go:10:2: error: undefined: store") == {("server.go", "10")}


RUST_START = """error[E0277]: the trait bound `for<'a> Router<AppState>: tower_service::Service<IncomingStream<'a>>` is not satisfied
   --> src/main.rs:32:27
    |
32  |     axum::serve(listener, app).await.expect("Server error");
"""


def test_rustc_s_place_on_the_line_after_the_error_and_the_harness_s_own_wording_are_one_cause():
    """Measured on one Rust run: "src/main.rs line 32: the trait bound ..." and a start whose output carried rustc's
    `--> src/main.rs:32:27` went to two fixers - the place sits on the line after `error[E0277]`."""
    compile_error = reported("notes-api/src/main.rs line 32: the trait bound `for<'a> Router<AppState>: "
                             "tower_service::Service<IncomingStream<'a>>` is not satisfied")
    start = reported("The product does not start for the acceptance suite, so no test can reach it.",
                     actual_behavior=f"{START_MARK} (`sh start.sh`): it stopped by itself with exit code 101. It wrote:\n"
                                     f"{RUST_START}")
    assert len(workflow._one_defect_per_cause([compile_error, start])) == 1


def test_a_warning_s_place_joins_nothing():
    assert workflow._error_locations("warning: unused import\n  --> src/lib.rs:3:5") == set()
