"""A file changed after its writer was recorded is not blamed on that writer (LF.1450).

Measured on a medium run (deep review 2026-11-25, decisions finding 10): a fixer's edit of `models.py` was refused with
"'specialist_ui_ux_2', a stage working alongside you, changed it since" - that builder had ended four hours earlier;
the fixer beside it in the same batch had written the file five seconds before, its write's record not yet made.
"""
from __future__ import annotations

import os
import time

from app.analysis.project_memory import record, who_changed

MODELS = "task-management-dashboard/task_management_dashboard/models.py"


def test_a_file_newer_than_its_writer_s_record_names_no_stage(tmp_path):
    (tmp_path / MODELS).parent.mkdir(parents=True)
    (tmp_path / MODELS).write_text("class User: ...\n", encoding="utf-8")
    record(tmp_path, MODELS, "specialist_ui_ux_2")
    later = time.time() + 60
    os.utime(tmp_path / MODELS, (later, later))

    assert who_changed(tmp_path, MODELS) == ""


def test_the_writer_just_recorded_is_still_named(tmp_path):
    (tmp_path / MODELS).parent.mkdir(parents=True)
    (tmp_path / MODELS).write_text("class User: ...\n", encoding="utf-8")
    record(tmp_path, MODELS, "defect_fix_2_4")

    assert who_changed(tmp_path, MODELS) == "defect_fix_2_4"
