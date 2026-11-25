"""A quality score per run, read from the stored product with no model call (plan PQ.10).

Measured on the product quality audit of 2026-11-25: eight stored products passed their hidden tests while one had
main text at 1.09:1 on its dark background, one styled controls by classes no element carried and never loaded its
token stylesheet, one had a schema twelve fields short of its specification, and one answered errors in two shapes.
Nothing measured any of it, so no change aimed at it could be kept or parked.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analysis import product_quality

TOKENS = """:root {
  color-scheme: light dark;
  --color-bg: #ffffff;
  --color-text: #1b1f24;
}
@media (prefers-color-scheme: dark) {
  :root { --color-bg: #0d1117; --color-text: #e6edf3; }
}
body { background: var(--color-bg); color: var(--color-text); }
"""


def _workspace(root: Path, files: dict[str, str], specification: str = "") -> Path:
    (root / ".project-directory").write_text("product\n")
    for name, text in files.items():
        path = root / "product" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "technical_specification.md").write_text(specification)
    return root


def _check(result: product_quality.QualityScore, part: str, name: str) -> product_quality.Check:
    (found,) = [c for p in result.parts if p.name == part for c in p.checks if c.name == name]
    return found


PAGE = """<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head><body>
<main><h1>Notes</h1><form><label for="title">Title</label><input id="title" type="text"></form>
<ul id="list"></ul><p class="empty-state">No notes yet</p><div role="alert"></div></main>
<script src="main.js"></script></body></html>"""


def test_a_text_colour_hard_coded_under_a_dark_scheme_fails_the_contrast_check(tmp_path):
    workspace = _workspace(tmp_path, {
        "index.html": PAGE, "main.js": "document.querySelector('#list');\n",
        "styles.css": TOKENS + ".note-title { color: #1a1a1a; }\n",
    })

    result = product_quality.score_workspace(workspace)

    contrast = _check(result, "interface", "contrast of declared colours")
    assert contrast.passed == 0.0
    (evidence,) = contrast.evidence
    assert "styles.css:10" in evidence and ".note-title" in evidence and "dark" in evidence and "1.09:1" in evidence
    assert _check(result, "interface", "raw colours where colour tokens exist").passed == 0.0


def test_tokens_used_throughout_pass_the_contrast_and_raw_colour_checks(tmp_path):
    workspace = _workspace(tmp_path, {
        "index.html": PAGE, "main.js": "document.querySelector('#list');\n",
        "styles.css": TOKENS + ".note-title { color: var(--color-text); }\n",
    })

    result = product_quality.score_workspace(workspace)

    assert _check(result, "interface", "contrast of declared colours").passed == 1.0
    assert _check(result, "interface", "raw colours where colour tokens exist").passed == 1.0


def test_a_class_nothing_carries_and_a_stylesheet_nothing_loads_are_found(tmp_path):
    workspace = _workspace(tmp_path, {
        "index.html": PAGE.replace('<link rel="stylesheet" href="styles.css">', '<link rel="stylesheet" href="app.css">'),
        "main.js": "document.querySelector('#list');\n",
        "styles.css": TOKENS,
        "app.css": ".add-control { padding: 1rem; }\n#list { margin: 0; }\n",
    })

    result = product_quality.score_workspace(workspace)

    unused = _check(result, "interface", "style rules styling nothing")
    assert unused.passed == 0.0 and [e.split(" ")[1] for e in unused.evidence] == [".add-control"]
    assert _check(result, "interface", "every stylesheet is loaded").evidence == ["styles.css: no page or script loads it"]


def test_a_field_without_a_label_is_found(tmp_path):
    page = PAGE.replace('<input id="title" type="text">', '<input id="title" type="text"><input name="tag">')
    workspace = _workspace(tmp_path, {"index.html": page, "main.js": "document.body;\n", "styles.css": TOKENS})

    labels = _check(product_quality.score_workspace(workspace), "interface", "fields with a label")

    assert labels.passed == 0.0 and len(labels.evidence) == 1 and 'name="tag"' in labels.evidence[0]


def test_a_page_with_no_words_for_an_empty_list_or_a_failure_loses_those_checks(tmp_path):
    page = PAGE.replace('<p class="empty-state">No notes yet</p><div role="alert"></div>', "")
    workspace = _workspace(tmp_path, {"index.html": page, "main.js": "fetch('/notes');\n", "styles.css": TOKENS})

    result = product_quality.score_workspace(workspace)

    assert [_check(result, "interface", name).passed for name in
            ("words for an empty list", "words for a request in flight", "words for a failure")] == [0.0, 0.0, 0.0]


SPECIFICATION = """# Technical Specification
## Domain Model
- Account: id (UUID), email (str, unique, required), password_hash (str), created_at (datetime).
## API and Event Contracts
- All error responses follow the contract: {"error_code": "<string>", "message": "<text>"}.
## Deployment
- Alembic migrations create the schema; indexes on email.
"""


def test_the_data_part_counts_the_fields_the_specification_adopted_and_what_it_asks_for(tmp_path):
    models = ("class Account(Base):\n    id = Column(Integer, primary_key=True)\n"
              "    email = Column(String, unique=True, index=True)\n")
    workspace = _workspace(tmp_path, {"app/models.py": models}, SPECIFICATION)

    result = product_quality.score_workspace(workspace)

    fields = _check(result, "data", "fields the domain model gives each record")
    assert fields.passed == 0.5 and fields.result == "2 of 4 declared"
    assert _check(result, "data", "ids of the kind stated").passed == 0.0
    assert _check(result, "data", "fields called unique declared unique").passed == 1.0
    assert _check(result, "data", "an index, as the specification asks").passed == 1.0
    assert _check(result, "data", "migrations, as the specification asks").passed == 0.0
    assert result.as_dict()["data"] == 50.0


SERVICE = """def create(body):
    if not body.get("title"):
        return JSONResponse(status_code=422, content={"error_code": "INVALID", "message": "title is required"})
    if exists(body):
        return JSONResponse(status_code=409, content={"error": "already there"})


def update(note, person):
    if note.owner != person:
        raise PermissionError("not yours")
"""


def test_two_error_shapes_a_shape_unlike_the_specification_s_and_a_refusal_never_answered_403_are_found(tmp_path):
    workspace = _workspace(tmp_path, {"app/routes.py": SERVICE}, SPECIFICATION)

    result = product_quality.score_workspace(workspace)

    shapes = _check(result, "service", "one error shape")
    assert shapes.passed == 0.0 and shapes.result == "2 shape(s)"
    assert any(e.startswith("{error_code, message} x1, first at app/routes.py:3") for e in shapes.evidence)
    assert _check(result, "service", "the error shape the specification states").passed == 0.0
    refusal = _check(result, "service", "a refusal the code raises answered 403")
    assert refusal.passed == 0.0 and refusal.evidence == ["app/routes.py: raises PermissionError"]
    assert result.counts["status codes"] == "409 422"


def test_a_product_with_no_page_has_no_interface_score_and_the_overall_is_the_mean_of_the_rest(tmp_path):
    service = SERVICE.replace('{"error": "already there"}', '{"error_code": "TAKEN", "message": "already there"}')
    workspace = _workspace(tmp_path, {"app/routes.py": service + "\n# 403 when the note is not yours\n"
                                      "def denied(): return JSONResponse(status_code=403, content={"
                                      '"error_code": "FORBIDDEN", "message": "not yours"})\n'}, SPECIFICATION)

    scores = product_quality.score_workspace(workspace).as_dict()

    assert scores["interface"] is None and scores["data"] == 0.0 and scores["service"] == 100.0
    assert scores["overall"] == 50.0


def test_the_command_prints_each_part_with_its_evidence_or_the_json_the_scoring_records(tmp_path, capsys):
    workspace = _workspace(tmp_path, {"app/routes.py": SERVICE}, SPECIFICATION)

    assert product_quality.main([str(workspace)]) == 0
    printed = capsys.readouterr().out
    assert product_quality.main([str(workspace), "--json"]) == 0
    recorded = json.loads(capsys.readouterr().out)

    assert "service: " in printed and "[fail] one error shape: 2 shape(s)" in printed and "app/routes.py:3" in printed
    assert set(recorded) >= {"overall", "interface", "data", "service", "parts", "counts"}
