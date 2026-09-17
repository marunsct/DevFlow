"""A named import of something `node:assert` or `node:test` does not export.

`assert` is `node:assert`'s *default* export, not a named one, so

    import { assert } from 'node:assert';

is not a failing assertion. The module never links and the file does not run
at all:

    SyntaxError: The requested module 'node:assert' does not provide an
    export named 'assert'

Four runs wrote it - 82e1dbdb five times, plus 499c771a, 551640d3 and
a7150a6c - against 351 writes of the correct `import { strict as assert }` in
the same corpus. It is a near-miss on a form that is otherwise everywhere,
which is exactly the kind a note at the write is for.

The export lists in `_REAL_EXPORTS` were read from the worker image on Node
20.20.2, and `test_every_allowed_name_is_really_exported` keeps them honest.
"""

from __future__ import annotations

import pytest

from app.analysis.test_discovery import (
    _REAL_EXPORTS,
    a_name_the_module_does_not_export,
)


@pytest.mark.parametrize(
    "source,name",
    [
        ("import { assert } from 'node:assert';", "assert"),
        ("import { expect } from 'node:test';", "expect"),
        ("import { equal, expect } from 'node:assert';", "expect"),
        ("import { assert } from 'node:assert/strict';", "assert"),
    ],
)
def test_a_name_that_is_not_exported_is_named(source, name):
    note = a_name_the_module_does_not_export("app.test.mjs", source)
    assert note is not None
    assert f"`{name}`" in note
    assert "does not provide an export named" in note


def test_it_says_the_file_does_not_run_at_all():
    note = a_name_the_module_does_not_export(
        "app.test.mjs", "import { assert } from 'node:assert';"
    )
    assert "not a failing assertion" in note
    assert "stops before any case runs" in note


def test_the_correction_for_assert_is_the_default_import():
    note = a_name_the_module_does_not_export(
        "app.test.mjs", "import { assert } from 'node:assert';"
    )
    assert "import assert from 'node:assert';" in note
    assert "it is the default export" in note


@pytest.mark.parametrize(
    "source",
    [
        "import assert from 'node:assert';",
        "import { strict as assert } from 'node:assert';",
        "import { strictEqual, deepStrictEqual, ok } from 'node:assert';",
        "import { equal } from 'node:assert/strict';",
        "import { test } from 'node:test';",
        "import { describe, it, before, beforeEach } from 'node:test';",
        "import { readFile } from 'node:fs/promises';",
        "import { addTask } from './app.js';",
        "import { JSDOM } from 'jsdom';",
    ],
)
def test_a_correct_import_says_nothing(source):
    assert a_name_the_module_does_not_export("app.test.mjs", source) is None


def test_a_file_that_is_not_javascript_is_left_alone():
    assert (
        a_name_the_module_does_not_export(
            "notes.md", "import { assert } from 'node:assert';"
        )
        is None
    )


def test_every_allowed_name_is_really_exported():
    """The lists came from the worker image; this keeps them from drifting.

    Runs against whatever Node is on the machine running the tests, so a
    version that drops or renames an export fails here rather than silently
    making the check wrong.
    """
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("no node on this machine")
    for module, names in _REAL_EXPORTS.items():
        found = subprocess.run(
            [node, "-e", f'import("{module}").then(m => console.log(JSON.stringify(Object.keys(m))))'],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if found.returncode != 0:
            pytest.skip(f"this node cannot import {module}")
        real = set(json.loads(found.stdout))
        missing = names - real
        assert not missing, f"{module} no longer exports {sorted(missing)}"
        # And the one that matters: `assert` must NOT be a named export, or
        # the whole check is wrong.
        if module.startswith("node:assert"):
            assert "assert" not in real
