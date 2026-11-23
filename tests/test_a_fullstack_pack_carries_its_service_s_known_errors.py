"""A full-stack pack carries its service language's known errors, and a doubly created index is one (found on a run).

Measured on one run: the composed full-stack pack (a page and a Python service) carried no known errors, so no Python
cause reached a fixer; every fix of the product was reverted for three rounds because the service no longer started -
`(sqlite3.OperationalError) index ix_... already exists` on `CREATE INDEX`.
"""
from __future__ import annotations

import re

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes
from app.stacks.packs import _python

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SAID = ("[WebServer] sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) index ix_records_owner already exists "
        "[WebServer] [SQL: CREATE INDEX ix_records_owner ON records (owner)]")


def _defect(text):
    return ReportedDefect(description="The product does not start for the acceptance suite, so no test can reach it.",
                          severity="blocking", reproduction_steps="npm run test:acceptance", expected_behavior="it starts",
                          actual_behavior=text, affected_files=[], owner="backend")


def test_the_python_full_stack_pack_has_the_python_known_errors():
    pack = pack_named("fullstack-react-fastapi")
    assert pack is not None
    assert set(_python.PYTHON_KNOWN_ERRORS) <= set(pack.known_errors)


def test_a_doubly_created_index_reaches_the_fixer_with_its_cause(tmp_path):
    contract.write(tmp_path, pack_named("fullstack-react-fastapi"), "records-app", "Records")

    (defect,) = with_known_causes(tmp_path, [_defect(SAID)])

    assert KNOWN_CAUSE in defect.actual_behavior and "Declare each index once" in defect.actual_behavior
    assert not BANNED.search(defect.actual_behavior.split(KNOWN_CAUSE, 1)[1])


def test_an_answer_that_says_a_record_already_exists_is_not_taken_for_it(tmp_path):
    contract.write(tmp_path, pack_named("fullstack-react-fastapi"), "records-app", "Records")

    (defect,) = with_known_causes(tmp_path, [_defect("answered 409: a record with that name already exists")])

    assert "Declare each index once" not in defect.actual_behavior
