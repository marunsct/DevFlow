"""What differs, counted by alignment rather than by position.

Comparing line 1 to line 1, line 2 to line 2 and so on is true only while the
two texts stay in step. One inserted line makes every line after it look
different, and the report is then mostly noise about lines that match.

Measured on one run: `specialist_testing_1` sent a 31-line passage
against a 29-line file that had gained two import lines at the top, and was
told 21 lines differed. Two of them did. It sent the same passage twice more
and finished the stage without making the edit. Edit find-misses are the
largest single category of costly failure in this harness, so the report being
readable is the difference between one call and four.
"""

from __future__ import annotations

from app.tools.repository import _how_it_differs

FILE = """// addTask.test.js
import assert from 'assert';
import { addTask } from '../app.js';
global.localStorage = { _store: new Map() };
let tasks = [];
tasks = addTask('t', 'd', tasks);
assert.strictEqual(tasks.length, 1);
"""

#: The same passage as the file, but still carrying the CommonJS line the file
#: no longer has - the shape that cost one run three calls.
SENT = """// addTask.test.js
const { addTask } = require('../app.js');
global.localStorage = { _store: new Map() };
let tasks = [];
tasks = addTask('t', 'd', tasks);
assert.strictEqual(tasks.length, 1);
"""


def _differences(message: str) -> list[str]:
    return [line for line in message.splitlines() if line.strip().startswith("you ")]


def test_an_insertion_does_not_make_every_later_line_differ():
    """The lines after an insertion match; only the insertion is a difference."""
    message = _how_it_differs(FILE, SENT)

    assert "These lines differ" in message
    # Four lines of the sent passage are identical to the file's and must not
    # be reported. Positional comparison reported all of them.
    assert len(_differences(message)) <= 3


def test_the_real_difference_is_still_named():
    message = _how_it_differs(FILE, SENT)

    assert "require('../app.js')" in message
    assert "import assert from 'assert';" in message


def test_a_line_the_file_does_not_have_says_so():
    sent = FILE.replace(
        "let tasks = [];\n", "let tasks = [];\nconst extra = require('node:util');\n"
    )

    message = _how_it_differs(FILE, sent)

    assert "not in the file" in message


def test_a_line_the_passage_left_out_is_named_with_its_number():
    sent = FILE.replace("let tasks = [];\n", "")

    message = _how_it_differs(FILE, sent)

    assert "you left out:" in message
    assert "let tasks = [];" in message


def test_an_exact_passage_reports_nothing():
    assert _how_it_differs(FILE, FILE) == ""


def test_a_single_wrong_character_is_still_reported():
    """The case the whole helper was written for - one run's `// ` prefix."""
    sent = FILE.replace("let tasks = [];", "// let tasks = [];")

    message = _how_it_differs(FILE, sent)

    assert "// let tasks = [];" in message
    assert "These lines differ" in message


def test_an_unrelated_passage_is_not_diffed_line_by_line():
    """Below the similarity floor the two are different passages, not a near miss."""
    assert _how_it_differs(FILE, "def python_function():\n    return 42\n") == ""
