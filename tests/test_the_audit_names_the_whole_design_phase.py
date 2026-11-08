"""The audit names the whole design phase, not only what the last fourteen stage switches still show (2026-11-08).

A run's escalation was reported as none: by the time it was read, the stage order no longer reached back to design.
"""
from __future__ import annotations

import ast
from pathlib import Path


def _design_line():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "audit_live.py").read_text()
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "design_line")
    space: dict = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "audit_live", "exec"), space)
    return space["design_line"]


def test_an_escalation_long_before_the_last_stages_is_named():
    design_line = _design_line()
    stages = ["principal_architect", "architecture_review", "principal_architect", "architecture_review", "escalation",
              "acceptance_author_0", *[f"defect_fix_{n}" for n in range(20)]]
    assert design_line(stages) == "design: 2 architecture review(s), escalated"


def test_a_design_with_no_escalation_says_so_and_a_later_escalation_does_not_count():
    design_line = _design_line()
    assert design_line(["principal_architect", "architecture_review", "acceptance_author_0", "escalation"]) == \
        "design: 1 architecture review(s), no escalation"
    assert design_line(["product_manager"]) == ""
