"""A model's sentence that happens to say "no external dependencies" does not forbid installing the product.

Measured on a gate run: the stack selector wrote that SQLite "suits this
single-user workload with no external dependencies" - no database server - and
every install of the product was refused as against the brief, including the
`pip install -e .` that would have installed its declared packages. The
refusal also offered Node's test modules to a Python project.
"""
from __future__ import annotations

from app.tools.sandbox import _refuse_an_install_the_brief_rules_out

RATIONALE = ("# Stack\n\nThe product is a Python-only HTTP API. SQLite is required by the constraints and suits "
             "this single-user workload with no external dependencies. passlib handles password hashing.\n")


def test_a_rationale_sentence_is_not_a_constraint(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technology_stack.md").write_text(RATIONALE)
    (tmp_path / "docs" / "product_intake.md").write_text("# Intake\n\n## Constraints\n\n- Python, SQLite, JSON over HTTP\n")
    assert _refuse_an_install_the_brief_rules_out([".venv/bin/python", "-m", "pip", "install", "-e", "."], str(tmp_path)) == ""


def test_a_stated_constraint_still_refuses_and_a_python_install_is_told_python_s_way(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text("# Intake\n\n## Constraints\n\n- No external dependencies: the standard library only\n")
    refusal = _refuse_an_install_the_brief_rules_out(["pip", "install", "requests"], str(tmp_path))
    assert "standard library only" in refusal and "unittest" in refusal and "requirements-dev.txt" in refusal
    assert "node:test" not in refusal
