"""Open mutation findings in one file go to one fixer, each settled by the harness after it (behind `MUTATION_GAPS_BUNDLED`).

Measured: three findings in one file, a comparison flipped on three lines, went to three fixers one after another -
38 model calls, about 15 minutes, after the product had passed every criterion. With the switch on, the first
finding's fixer is handed the others in its file too; after its fix the harness checks each one itself and closes
those the unit tests now notice, leaving the rest for their own fixer. Off, each is fixed alone, as before.
"""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from app.acceptance import mutation_guided
from app.agents.specialists import SpecialistOutput
from app.graph import mutation_gaps_bundled
from app.graph.workflow import MOST_BUNDLED_DEFECTS, _bundle_co_defects
from app.sprint import RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _finding(line: int, file: str = "src/Service.php", owner: str = "testing"):
    found = mutation_guided.defect({"file": file, "line": line, "column": 20, "original": "||", "replacement": "&&",
                                    "text": f"        return $a || $b; // {line}"})
    return found.model_copy(update={"owner": owner})


def _the_round():
    return [_finding(54), _finding(60), _finding(95), _finding(12, file="src/Other.php"), _finding(70, owner="backend")]


@pytest.mark.parametrize("switch", ["on", "off"])
def test_findings_in_the_file_being_fixed_are_bundled_only_with_the_switch_on(monkeypatch, switch):
    monkeypatch.setenv("MUTATION_GAPS_BUNDLED", switch)
    cycle = RemediationCycle(sprint_goal="g", defects=[*_the_round(), _finding(99)])

    bundled = [pos for pos, _ in _bundle_co_defects(cycle, 0)]

    # Same file and owner, after it, at most `MOST_BUNDLED_DEFECTS`; never another file's or another role's.
    assert bundled == ([1, 2] if switch == "on" else []) and MOST_BUNDLED_DEFECTS == 2


def test_a_fixed_finding_is_not_bundled_and_a_defect_that_is_no_finding_bundles_as_before(monkeypatch):
    monkeypatch.setenv("MUTATION_GAPS_BUNDLED", "on")
    round_ = _the_round()
    round_[1] = round_[1].model_copy(update={"status": "fixed"})

    assert [pos for pos, _ in _bundle_co_defects(RemediationCycle(sprint_goal="g", defects=round_), 0)] == [2]
    assert _bundle_co_defects(RemediationCycle(sprint_goal="g", defects=round_), 3) == []


def _fix_the_first(tmp_path, monkeypatch, switch: str, notices: set[int]):
    from workflow_nodes import a_fix_stage

    monkeypatch.setenv("MUTATION_GAPS_BUNDLED", switch)
    checked: list[int] = []

    def settled(root, defect, **kwargs):
        line = mutation_guided.site_of(defect)["line"]
        checked.append(line)
        return line in notices

    with patch.object(mutation_guided, "settled", settled), \
         patch("app.graph.workflow.mutation_guided.settled", settled):
        update, asked = a_fix_stage(
            tmp_path, _the_round(),
            answer=SpecialistOutput(changed_files=["tests/ServiceTest.php"], tests=["tests/ServiceTest.php"]),
        )
    return update, asked, checked


def test_on_the_fixer_is_shown_each_bundled_change_and_what_settles_it(tmp_path, monkeypatch):
    _, asked, _ = _fix_the_first(tmp_path, monkeypatch, "on", {54})

    request = asked["requests"][0]
    assert mutation_gaps_bundled.SAYS in request
    for line in (60, 95):
        assert f"`src/Service.php` line {line}, column 20: `||` made `&&`." in request
    assert "Settled when a unit test fails with `&&` there and passes with `||`." in request
    assert "line 12," not in request and "line 70," not in request
    # Listed once: not again among the other findings in its file.
    assert request.count("line 60, column 20") == 1


def test_off_the_fixer_is_shown_no_bundle(tmp_path, monkeypatch):
    _, asked, _ = _fix_the_first(tmp_path, monkeypatch, "off", {54})

    assert mutation_gaps_bundled.SAYS not in asked["requests"][0]


def test_on_a_bundled_finding_the_tests_now_notice_is_closed_and_one_they_do_not_stays_open(tmp_path, monkeypatch):
    update, _, checked = _fix_the_first(tmp_path, monkeypatch, "on", {54, 60})

    statuses = [d.status for d in update["remediation"].defects]
    assert statuses[:3] == ["fixed", "fixed", "open"] and statuses[3:] == ["open", "open"]
    assert sorted(checked) == [54, 60, 95]
    assert update["remediation"].defects[1].verified_by == "the harness's mutation check"


def test_on_a_bundled_finding_is_never_closed_on_the_strength_of_the_first_one_s_answer(tmp_path, monkeypatch):
    update, _, _ = _fix_the_first(tmp_path, monkeypatch, "on", {54})

    assert [d.status for d in update["remediation"].defects][:3] == ["fixed", "open", "open"]


def test_off_only_the_finding_fixed_is_checked(tmp_path, monkeypatch):
    update, _, checked = _fix_the_first(tmp_path, monkeypatch, "off", {54, 60, 95})

    assert checked == [54]
    assert [d.status for d in update["remediation"].defects][:3] == ["fixed", "open", "open"]


def test_a_test_written_for_a_bundled_change_is_kept_though_it_misses_the_first(tmp_path, monkeypatch):
    from app.acceptance import mutation_retention

    monkeypatch.setenv("MUTATION_TEST_RETENTION", "on")
    put_back: list[list[str]] = []
    monkeypatch.setattr(mutation_retention, "_forget", lambda run, stage: {"base": "abc", "failing": None})
    monkeypatch.setattr(mutation_retention, "_put_back", lambda root, base, paths, why, stage: put_back.append(paths) or paths)
    monkeypatch.setattr(mutation_retention, "_created_by_the_fix", lambda root, base, path: True)
    monkeypatch.setattr("app.ci.changed_since", lambda root, base: ["tests/ServiceTest.php"])
    monkeypatch.setattr("app.ci.load", lambda root, label: None)

    assert mutation_retention.judged(tmp_path, "r", "s", lambda: False, keeps=lambda: True) == (False, "")
    assert put_back == []
    assert mutation_retention.judged(tmp_path, "r", "s", lambda: False, keeps=lambda: False)[1]
    assert put_back == [["tests/ServiceTest.php"]]


def test_the_bundled_section_bans_the_words():
    told = mutation_gaps_bundled.section([(1, _finding(60)), (2, _finding(95))])

    assert told and not BANNED.search(told), told
    assert mutation_gaps_bundled.section([]) == ""


def test_the_switch_s_firing_signal_is_the_text_the_request_carries():
    from app.observability.switch_firing import SIGNALS

    assert SIGNALS["MUTATION_GAPS_BUNDLED"] in mutation_gaps_bundled.section([(1, _finding(60))])
