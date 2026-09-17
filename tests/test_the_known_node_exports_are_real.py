"""`_NODE_NAMED_EXPORTS` must keep matching the Node that runs the products.

`_unknown_named_imports` accuses an import of naming something that does not
exist. Its docstring is explicit that a false accusation on a write costs more
than a missed one, and the whole accusation rests on this table being right
about the runtime. A Node release that renames an export would turn it into a
source of confident wrong notes with nothing to catch it.

So the table is checked against the interpreter rather than trusted. Written
after building a second, redundant copy of this check and discovering the
original only when both notes appeared on one write - the table was already
correct; what it lacked was anything keeping it that way.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from app.analysis.syntax_balance import _NODE_NAMED_EXPORTS


def _exports_of(module: str) -> set[str] | None:
    node = shutil.which("node")
    if node is None:
        return None
    found = subprocess.run(
        [node, "-e", f'import("{module}").then(m => console.log(JSON.stringify(Object.keys(m))))'],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if found.returncode != 0:
        return None
    return set(json.loads(found.stdout))


@pytest.mark.parametrize("module", sorted(_NODE_NAMED_EXPORTS))
def test_nothing_in_the_table_is_missing_from_node(module):
    """Every name the table calls valid must really be importable.

    A name here that Node does not export is the dangerous direction: the
    check would stay silent on an import that cannot work.
    """
    real = _exports_of(module)
    if real is None:
        pytest.skip(f"this machine cannot import {module}")
    # `snapshot` is in the table and absent before Node 22. Allowed: a name
    # the table has and the runtime lacks only costs a missed note, never a
    # wrong one, and it keeps the table right on newer runtimes.
    missing = _NODE_NAMED_EXPORTS[module] - real - {"snapshot"}
    assert not missing, f"{module} does not export {sorted(missing)}"


@pytest.mark.parametrize("module", ["node:assert", "assert", "node:assert/strict"])
def test_assert_is_still_not_a_named_export(module):
    """The premise of the check's most specific message.

    If a future Node adds `assert` as a named export, `import { assert } from
    'node:assert'` starts working and the note becomes wrong.
    """
    real = _exports_of(module)
    if real is None:
        pytest.skip(f"this machine cannot import {module}")
    assert "assert" not in real
    assert "assert" not in _NODE_NAMED_EXPORTS[module]


def test_the_note_says_the_file_does_not_load():
    """It is a link-time SyntaxError, not a failing assertion at runtime.

    A stage told an import "will fail at runtime" looks for the failure in
    what the test asserts; the file never got that far.
    """
    from app.analysis.syntax_balance import _unknown_named_imports

    note = _unknown_named_imports("import { assert } from 'node:assert';\n")
    assert note is not None
    assert "stops the file loading" in note
    assert "SyntaxError" in note
