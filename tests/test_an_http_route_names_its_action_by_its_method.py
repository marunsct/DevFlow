"""A service's PUT or PATCH route is its update, whatever its handler is called.

Measured on one run: the brief asked for `PUT /notes/{id}`, the run's documents called it "update", and the product
served it as `app.put('/notes/:id', ...)` - every hidden test passed. The last-sprint check found no word "update" in
the code, called the brief undelivered, and the run spent an escalation and a second round of planning and reviews.
"""
from __future__ import annotations

from app.analysis.integration_checks import _a_required_action_nothing_implements

BRIEF = "# Notes\n- Users can create, update and delete notes.\n"


def _product(tmp_path, code):
    source = tmp_path / "notes" / "src"
    source.mkdir(parents=True)
    (source / "app.ts").write_text(code)
    return [source / "app.ts"]


def test_a_put_route_is_the_update(tmp_path):
    files = _product(tmp_path, "app.post('/notes', h);\napp.put('/notes/:id', async (c) => c.json({}));\n"
                               "app.delete('/notes/:id', h);\n")
    assert _a_required_action_nothing_implements(files, tmp_path, BRIEF) == []


def test_a_patch_route_in_another_language_is_the_update_too(tmp_path):
    files = _product(tmp_path, "@app.post('/notes')\ndef make(): ...\n@router.patch('/notes/{id}')\ndef change(): ...\n"
                               "@app.delete('/notes/{id}')\ndef drop(): ...\n")
    assert _a_required_action_nothing_implements(files, tmp_path, BRIEF) == []


def test_a_service_with_no_such_route_still_lacks_it(tmp_path):
    files = _product(tmp_path, "app.post('/notes', h);\napp.get('/notes/:id', h);\napp.delete('/notes/:id', h);\n")
    problems = _a_required_action_nothing_implements(files, tmp_path, BRIEF)
    assert len(problems) == 1 and "`update`" in problems[0]
