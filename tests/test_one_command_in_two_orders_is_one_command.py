"""A specification that gives one command two results by the order of its options alone is sent back.

Measured on two runs of one brief, both false acceptances: `--top N --json` printed only the top words and
`--json --top N` the counts as well; the suite tested both, the product printed the counts, and the hidden test failed.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.acceptance.interface_contract import commands_that_differ_only_in_order
from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SPEC = (
    '- AC-4 command python -m wordstats <file> --top N --json -> stdout {"top": [{"word": <w>, "count": <c>}]}, exit 0\n'
    '- AC-9 command python -m wordstats <file> --json --top N -> stdout {"words": 6, "lines": 3, "top": [...]}, exit 0\n'
    "- AC-1 command python -m wordstats <file> -> exit 0\n"
)


def test_the_same_options_in_another_order_with_another_result_are_found():
    [(a, b)] = commands_that_differ_only_in_order(SPEC)
    assert "--top N --json" in a and "--json --top N" in b


def test_the_same_result_or_other_arguments_are_not():
    same = SPEC.replace('{"words": 6, "lines": 3, "top": [...]}', '{"top": [{"word": <w>, "count": <c>}]}')
    assert commands_that_differ_only_in_order(same) == []
    assert commands_that_differ_only_in_order("- AC-1 command tool a -> 1\n- AC-2 command tool b -> 2\n") == []


def test_the_design_review_is_given_it_once_as_a_major_finding():
    state = {"architecture_revision_count": 0}
    finding = workflow._the_same_command_in_another_order(state, SPEC)
    assert finding.severity == "major" and "order of its options" in finding.description
    assert not BANNED.search(finding.description + finding.required_remediation)
    assert workflow._the_same_command_in_another_order({**state, "specification_command_order_checked": True}, SPEC) is None
    assert 'fired.append("order")' in inspect.getsource(workflow)
    assert "order" in workflow._THE_HARNESS_S_DESIGN_CHECKS
