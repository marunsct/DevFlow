"""A language service's import finding that its fixer's own run showed false is a suspected false finding, not a
rewrite (LF.1401, the rest).

Measured on a medium run: the service said `"settings" is unknown import symbol` in a router; the fixer ran
`python -c "from app.routers.auth import router; from app.config import settings; ..."`, which exited 0, and gave up,
and the rewrite after the surrender was sent at a file whose imports work. The fixer's commands and their results
below are that attempt's, as the transcript holds them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import the_fix_stage

from app.agents.specialists import SpecialistOutput
from app.sprint import Defect

ROUTER = "task-management-dashboard/backend/app/routers/auth.py"
UNDERLINED = (f'{ROUTER} line 10: "settings" is unknown import symbol - this fails when the code runs. The same '
              f'problem, as other checks reported it: - [language service] {ROUTER} line 12: "RefreshToken" is '
              "unknown import symbol")
RAN = [json.loads(line) for line in (Path(__file__).parent / "captured"
       / "transcript-a-fixer-runs-the-imports-the-language-service-underlined.jsonl").read_text().splitlines()]


@pytest.fixture(autouse=True)
def _a_run_with_a_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("SURRENDER_TO_REWRITE", "on")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")


def _workspace(root: Path) -> None:
    (root / ROUTER).parent.mkdir(parents=True, exist_ok=True)
    (root / ROUTER).write_text("from app.config import settings\nfrom app.models import RefreshToken, User\n")


def _the_attempt(entries):
    """The fixer's commands of the attempt, recorded as it runs."""
    from app.observability.transcript import record

    def during(stage):
        for entry in entries:
            record("r", stage, entry["kind"], **{k: v for k, v in entry.items() if k not in ("at", "stage", "kind")})

    return during


def _gave_up(root, entries):
    from app.observability.transcript import read_transcript

    defect = Defect(description=UNDERLINED, severity="major", owner="backend", affected_files=[ROUTER],
                    reproduction_steps=f"Read {ROUTER} at line 10.", expected_behavior="Every import names something.",
                    actual_behavior='"settings" is unknown import symbol (Pyright, as an IDE would underline it)')
    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, defect), real_files=True,
                                answer=SpecialistOutput(changed_files=[]), during=_the_attempt(entries))
    said = [r["detail"] for r in read_transcript("r", {"defect"}) if r.get("event") == "rewrite after surrender"]
    return seen, said


def test_an_import_finding_its_fixer_ran_is_not_rewritten(tmp_path):
    _workspace(tmp_path)

    seen, said = _gave_up(tmp_path, RAN)

    assert seen.rewrites == []
    assert any("suspected false finding" in line and "from app.config import settings" in line for line in said)


def test_the_next_gate_words_it_as_the_service_s_while_the_file_is_unchanged(tmp_path):
    from app.analysis.checker_contradicted import contradicted

    _workspace(tmp_path)
    _gave_up(tmp_path, RAN)

    assert "exited 0" in contradicted(ROUTER, '"settings" is unknown import symbol', None, tmp_path)
    (tmp_path / ROUTER).write_text("from app.config import settings, other\n")
    assert contradicted(ROUTER, '"settings" is unknown import symbol', None, tmp_path) == ""


def test_a_fixer_whose_import_failed_still_gets_the_rewrite(tmp_path):
    _workspace(tmp_path)
    failed = [dict(entry, content=entry["content"].replace('"returncode": "0"', '"returncode": "1"'))
              if entry["kind"] == "tool_result" else entry for entry in RAN]

    seen, _ = _gave_up(tmp_path, failed)

    assert len(seen.rewrites) == 1
