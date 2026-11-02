"""A page's root-relative reference is looked for in every folder up to the project.

Measured on one run: `static/index.html` loaded `/static/app.js`, which the service serves from `static/app.js`. The
check looked only beside the page, in `static/static/`, and raised the same false defect in four fix rounds.
"""
from __future__ import annotations

from app.analysis.integration_checks import _broken_local_references


def _page(root, target):
    page = root / "app" / "static" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text(f'<script src="{target}"></script>')
    return page


def test_a_root_relative_reference_to_a_file_higher_up_is_found(tmp_path):
    page = _page(tmp_path, "/static/app.js")
    (page.parent / "app.js").write_text("run();\n")

    assert _broken_local_references([page], tmp_path) == []


def test_a_reference_to_nothing_is_still_reported(tmp_path):
    page = _page(tmp_path, "/static/gone.js")

    assert "does not exist" in _broken_local_references([page], tmp_path)[0]


def test_a_plain_relative_reference_is_only_looked_for_beside_the_page(tmp_path):
    page = _page(tmp_path, "static/app.js")
    (page.parent / "app.js").write_text("run();\n")

    assert "does not exist" in _broken_local_references([page], tmp_path)[0]
